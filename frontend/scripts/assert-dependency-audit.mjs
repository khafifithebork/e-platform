/** npm remains the scanner. Exceptions apply to exact development-only lockfile paths. */
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const levels = ["info", "low", "moderate", "high", "critical"];
const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const text = (value) => typeof value === "string" && value.trim().length > 0;
const high = (severity) => levels.indexOf(severity) >= 3;
function requireValid(condition, message) {
  if (!condition) throw new Error(message);
}

/**
 * The audit could not be performed — as distinct from the audit finding something.
 *
 * **These were indistinguishable until 2026-10-30.** Every throw in this file surfaced
 * as `AUDIT FAILED: <message>`, so a registry hiccup printed
 * `AUDIT FAILED: Invalid audit report.` with exit 1 and no advisory named — on a job
 * that gates staging and transitively production. Observed in roughly one run in four.
 * Somebody reading that reasonably concludes a dependency is vulnerable and goes looking
 * for which; there is nothing to find.
 *
 * Both outcomes still fail, and that is deliberate: a gate that passes when it could not
 * audit is worse than one that is occasionally noisy (ADR-022 §3). What changes is that
 * the two now say which they are.
 */
export class AuditUnavailable extends Error {}

/** Attempts at obtaining a trustworthy report before giving up. */
export const AUDIT_ATTEMPTS = 3;

/** Backoff between attempts, in milliseconds. Short: CI minutes are not free. */
const AUDIT_BACKOFF_MS = [2000, 5000];

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

export function parseAuditResult(result) {
  requireValid(!result.error && !result.signal && [0, 1].includes(result.status), "Audit command failed; no result can be trusted.");
  let report;
  try {
    report = JSON.parse(result.stdout);
  } catch {
    throw new Error("Audit command returned empty or invalid JSON.");
  }
  validateReport(report);
  const counts = report.metadata.vulnerabilities;
  requireValid(result.status === (counts.high + counts.critical > 0 ? 1 : 0), "Audit exit code disagrees with its report.");
  return report;
}

function validateReport(report) {
  requireValid(object(report) && !report.error && report.auditReportVersion === 2 && object(report.vulnerabilities), "Invalid audit report.");
  const counts = report.metadata?.vulnerabilities;
  requireValid(object(counts) && report.metadata?.dependencies?.total > 0, "Invalid audit metadata or empty dependency inventory.");
  const actual = Object.fromEntries(levels.map((level) => [level, 0]));
  for (const [name, finding] of Object.entries(report.vulnerabilities)) {
    requireValid(object(finding) && finding.name === name && levels.includes(finding.severity), "Invalid audit finding.");
    actual[finding.severity]++;
    requireValid(Array.isArray(finding.nodes) && finding.nodes.length > 0 && finding.nodes.every(text), "Audit finding has no installed nodes.");
    requireValid(Array.isArray(finding.via) && finding.via.length > 0, "Audit finding has no cause.");
    for (const via of finding.via) {
      if (typeof via === "string") {
        requireValid(object(report.vulnerabilities[via]), "Audit transitive cause is missing.");
      } else {
        requireValid(object(via) && levels.includes(via.severity) && text(via.url) && text(via.title), "Invalid audit advisory.");
      }
    }
  }
  requireValid(levels.every((level) => counts[level] === actual[level]) && counts.total === Object.keys(report.vulnerabilities).length, "Audit counts disagree with findings.");
  // A transitive finding must terminate in an advisory, not in a cycle of names.
  function causes(name, stack = []) {
    requireValid(!stack.includes(name), "Audit cause cycle.");
    const finding = report.vulnerabilities[name];
    return finding.via.flatMap((via) => typeof via === "string" ? causes(via, [...stack, name]) : [via]);
  }
  for (const name of Object.keys(report.vulnerabilities)) {
    const finding = report.vulnerabilities[name];
    requireValid(!high(finding.severity) || causes(name).some((via) => high(via.severity)), "Audit severity has no matching advisory cause.");
  }
}

function validateExceptions(entries, now) {
  requireValid(Array.isArray(entries), "Invalid exception list.");
  const seen = new Set();
  for (const entry of entries) {
    requireValid(object(entry) && /^GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$/.test(entry.advisory)
      && Array.isArray(entry.path) && entry.path.length > 0 && entry.path.every((part) => text(part) && !part.includes(">") && !part.includes("*"))
      && text(entry.reason) && text(entry.triager) && /^\d{4}-\d{2}-\d{2}$/.test(entry.reviewBy), "Invalid exception: advisory, exact path, reason, triager and reviewBy are required.");
    const deadline = new Date(`${entry.reviewBy}T23:59:59.999Z`);
    requireValid(Number.isFinite(deadline.getTime()) && deadline.toISOString().startsWith(entry.reviewBy), "Invalid exception review date.");
    requireValid(now <= deadline, `Expired exception: ${entry.advisory}; review with ${entry.triager}.`);
    const key = `${entry.advisory}|${entry.path.join(">")}`;
    requireValid(!seen.has(key), "Duplicate exception.");
    seen.add(key);
  }
}

/** Resolve installed paths rather than trusting npm audit's package-level cause graph. */
function installedPaths(lock) {
  requireValid(object(lock) && lock.lockfileVersion === 3 && object(lock.packages) && object(lock.packages[""]), "Invalid lockfile; version 3 with a root package is required.");
  const parents = new Map();
  const packages = lock.packages;
  for (const [location, pkg] of Object.entries(packages)) {
    requireValid(object(pkg) && !pkg.link, "Unsupported linked package in lockfile.");
    const dependencies = { ...pkg.dependencies, ...pkg.optionalDependencies, ...pkg.peerDependencies, ...(location === "" ? pkg.devDependencies : {}) };
    for (const name of Object.keys(dependencies)) {
      let directory = location;
      let target;
      while (true) {
        const candidate = posix.join(directory, "node_modules", name);
        if (Object.hasOwn(packages, candidate)) { target = candidate; break; }
        if (!directory) break;
        const parent = posix.dirname(directory);
        directory = parent === "." ? "" : parent;
      }
      if (!target) {
        // Optional and peer packages may legitimately be absent from an installed tree.
        requireValid(Object.hasOwn(pkg.optionalDependencies ?? {}, name) || Object.hasOwn(pkg.peerDependencies ?? {}, name), `Incomplete lockfile dependency: ${location}>${name}`);
        continue;
      }
      const edges = parents.get(target) ?? [];
      edges.push({ location, name });
      parents.set(target, edges);
    }
  }
  return (node) => {
    let visits = 0;
    function walk(current, stack) {
      requireValid(++visits <= 10000, "Lockfile path limit exceeded; manual review required.");
      requireValid(!stack.includes(current), "Lockfile dependency cycle; cannot safely exempt this path.");
      requireValid(object(packages[current]) && parents.has(current), `Unresolved lockfile node: ${current}`);
      return parents.get(current).flatMap(({ location, name }) => {
        const dev = packages[current].dev === true;
        if (location === "") {
          const root = packages[""];
          const devRoot = Object.hasOwn(root.devDependencies ?? {}, name)
            && !Object.hasOwn(root.dependencies ?? {}, name)
            && !Object.hasOwn(root.optionalDependencies ?? {}, name)
            && !Object.hasOwn(root.peerDependencies ?? {}, name);
          return [{ names: [name], dev: dev && devRoot }];
        }
        return walk(location, [...stack, current]).map((path) => ({ names: [...path.names, name], dev: path.dev && dev }));
      });
    }
    return walk(node, []);
  };
}

export function evaluateAudit(report, lock, exceptions, now = new Date()) {
  validateReport(report);
  validateExceptions(exceptions, now);
  const pathsTo = installedPaths(lock);
  const failures = new Set();
  const suppressed = new Set();
  const used = new Set();
  for (const finding of Object.values(report.vulnerabilities)) {
    for (const advisory of finding.via) {
      if (typeof advisory === "string" || !high(advisory.severity)) continue;
      const id = /^https:\/\/github\.com\/advisories\/(GHSA-[a-z0-9-]+)$/.exec(advisory.url)?.[1];
      const candidates = exceptions.filter((entry) => entry.advisory === id);
      if (!candidates.length) {
        failures.add(`${id ?? advisory.url}: ${advisory.title}`);
        continue;
      }
      for (const node of finding.nodes) {
        for (const path of pathsTo(node)) {
          const label = `${id}|${path.names.join(">")}`;
          const entry = candidates.find((entry) => entry.path.join(">") === path.names.join(">"));
          if (entry && path.dev) {
            used.add(entry);
            suppressed.add(`${label} — triager: ${entry.triager}; review by ${entry.reviewBy}; ${entry.reason}`);
          } else {
            failures.add(`${label}${path.dev ? "" : " (not development-only)"}`);
          }
        }
      }
    }
  }
  return {
    failures: [...failures],
    suppressed: [...suppressed],
    stale: exceptions.filter((entry) => !used.has(entry)).map((entry) => `${entry.advisory}|${entry.path.join(">")}`),
  };
}

/** Runs npm. Fixed command only; no user-controlled arguments reach the Windows shell. */
function runAudit(root) {
  return spawnSync(process.platform === "win32" ? "npm.cmd" : "npm", ["audit", "--json", "--audit-level=high"], {
    cwd: root, encoding: "utf8", shell: process.platform === "win32", timeout: 120000, maxBuffer: 16 * 1024 * 1024,
  });
}

/**
 * A report worth evaluating, or `AuditUnavailable`.
 *
 * **Retried, because the thing that fails here is a network call.** `npm audit` posts the
 * dependency tree to the registry, and a 5xx or a truncated body makes `parseAuditResult`
 * throw. Nothing about the project changed between attempts, so trying again is the
 * correct response — where retrying a malformed `audit-allowlist.json` would just be
 * slower.
 *
 * **That split is the whole design.** Only obtaining the report is retried. Everything
 * `evaluateAudit` does — paths, exceptions, expiry — is deterministic given the inputs,
 * so a failure there is a real problem and is reported on the first attempt.
 *
 * A valid report **is returned immediately even when it contains findings**. Retrying a
 * genuine vulnerability would be the dangerous version of this change: three attempts,
 * three identical findings, and a message implying flakiness. The tests pin that.
 *
 * `run` and `wait` are injectable so the tests can exercise the retry without a network
 * or a real delay.
 */
export async function obtainReport(run, { attempts = AUDIT_ATTEMPTS, wait = sleep } = {}) {
  const problems = [];

  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      return parseAuditResult(run());
    } catch (error) {
      problems.push(error.message);
      if (attempt === attempts) break;
      console.warn(`AUDIT RETRY ${attempt}/${attempts - 1}: ${error.message}`);
      await wait(AUDIT_BACKOFF_MS[Math.min(attempt - 1, AUDIT_BACKOFF_MS.length - 1)]);
    }
  }

  // Every distinct reason, not just the last: a tree that fails three different ways is a
  // different problem from one that fails the same way three times, and the message is all
  // anybody reading CI gets.
  throw new AuditUnavailable(
    `Audit could not be performed in ${attempts} attempts: ${[...new Set(problems)].join("; ")}`,
  );
}

async function main() {
  const root = dirname(dirname(fileURLToPath(import.meta.url)));
  const read = (name) => JSON.parse(readFileSync(join(root, name), "utf8"));
  const report = await obtainReport(() => runAudit(root));
  const audit = evaluateAudit(report, read("package-lock.json"), read("audit-allowlist.json"));
  for (const message of audit.suppressed) console.warn(`ACCEPTED EXCEPTION: ${message}`);
  for (const message of audit.stale) console.warn(`STALE EXCEPTION: ${message}; remove or re-triage.`);
  for (const message of audit.failures) console.error(`AUDIT FAILED: ${message}`);
  if (audit.failures.length) process.exitCode = 1;
  else console.log("Dependency audit passed; all high/critical findings accounted for.");
}

/**
 * How a fatal error is rendered and exited on.
 *
 * Two prefixes and two exit codes, **both non-zero**:
 *
 * - `AUDIT COULD NOT RUN`, exit 2 — the gate never got a report it could trust.
 * - `AUDIT FAILED`, exit 1 — it did, and the report was not acceptable.
 *
 * **Exit 2 still fails the job, and must.** CI treats any non-zero as failure, which is the
 * fail-closed behaviour ADR-022 §3 requires; the code exists so a human, or a later retry
 * wrapper, can tell a registry outage from a vulnerability without parsing prose.
 *
 * Exported because it was inline in the entry point, where nothing could assert it —
 * ADR-023 §1: that made the exit code a decision rather than a control.
 */
export function classifyFatal(error) {
  const unavailable = error instanceof AuditUnavailable;
  return { message: `${unavailable ? "AUDIT COULD NOT RUN" : "AUDIT FAILED"}: ${error.message}`, exitCode: unavailable ? 2 : 1 };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    const { message, exitCode } = classifyFatal(error);
    console.error(message);
    process.exitCode = exitCode;
  });
}
