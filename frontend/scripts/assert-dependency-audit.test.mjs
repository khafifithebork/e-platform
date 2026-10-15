import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { evaluateAudit, parseAuditResult } from "./assert-dependency-audit.mjs";

const recorded = JSON.parse(readFileSync(new URL("./fixtures/npm-audit-2026-10-08.json", import.meta.url), "utf8"));
const lock = JSON.parse(readFileSync(new URL("../package-lock.json", import.meta.url), "utf8"));
const exceptions = JSON.parse(readFileSync(new URL("../audit-allowlist.json", import.meta.url), "utf8"));
const now = new Date("2026-10-08T00:00:00Z");
const clone = (value) => structuredClone(value);
const run = (report = recorded, entries = exceptions, tree = lock) => evaluateAudit(report, tree, entries, now);

function bracesOnly() {
  const report = clone(recorded);
  const names = new Set(["eslint-config-next", "@next/eslint-plugin-next", "fast-glob", "micromatch", "braces"]);
  report.vulnerabilities = Object.fromEntries(Object.entries(report.vulnerabilities).filter(([name]) => names.has(name)));
  report.metadata.vulnerabilities = { info: 0, low: 0, moderate: 0, high: 5, critical: 0, total: 5 };
  return report;
}

test("rejects_unapproved_findings in the recorded npm response", () => {
  const result = run(recorded, []);
  assert.equal(result.failures.length, 4);
  assert.ok(result.failures.some((item) => item.includes("GHSA-vfj7-8cjw-p6xm")));
});

test("accepts_only_exact_allowed_path and resolves the five reported packages", () => {
  const result = run(bracesOnly());
  assert.deepEqual(result.failures, []);
  assert.equal(result.suppressed.length, 1);
  assert.match(result.suppressed[0], /eslint-config-next.*braces/);
});

test("still rejects the three other recorded advisories", () => {
  const result = run();
  assert.equal(result.failures.length, 3);
  assert.equal(result.suppressed.length, 1);
});

test("rejects_same_advisory_on_other_paths even through a parent absent from audit findings", () => {
  const tree = clone(lock);
  tree.packages[""].devDependencies["another-parent"] = "1.0.0";
  tree.packages["node_modules/another-parent"] = { version: "1.0.0", dev: true, dependencies: { braces: "3.0.3" } };
  assert.ok(run(bracesOnly(), exceptions, tree).failures.some((item) => item.includes("another-parent>braces")));
});

test("rejects a near-miss path", () => {
  const entries = clone(exceptions);
  entries[0].path[0] = "wrong-parent";
  assert.equal(run(bracesOnly(), entries).failures.length, 1);
});

test("rejects production use on the otherwise allowed path", () => {
  const tree = clone(lock);
  delete tree.packages["node_modules/braces"].dev;
  assert.equal(run(bracesOnly(), exceptions, tree).failures.length, 1);
});

test("rejects a runtime root even if a stale lockfile still marks its nodes dev", () => {
  const tree = clone(lock);
  tree.packages[""].dependencies["eslint-config-next"] = tree.packages[""].devDependencies["eslint-config-next"];
  delete tree.packages[""].devDependencies["eslint-config-next"];
  assert.equal(run(bracesOnly(), exceptions, tree).failures.length, 1);
});

test("also checks optional and peer paths to the same advisory", () => {
  for (const kind of ["optionalDependencies", "peerDependencies"]) {
    const tree = clone(lock);
    tree.packages[""].devDependencies["another-parent"] = "1.0.0";
    tree.packages["node_modules/another-parent"] = { version: "1.0.0", dev: true, [kind]: { braces: "3.0.3" } };
    assert.ok(run(bracesOnly(), exceptions, tree).failures.some((item) => item.includes("another-parent>braces")));
  }
});

test("reports_stale_exceptions on a valid clean report", () => {
  const report = bracesOnly();
  report.vulnerabilities = {};
  report.metadata.vulnerabilities = { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 };
  const result = run(report);
  assert.deepEqual(result.failures, []);
  assert.equal(result.stale.length, 1);
});

test("requires_reason_and_triager and a bounded review date", () => {
  for (const key of ["reason", "triager", "reviewBy"]) {
    const entries = clone(exceptions);
    delete entries[0][key];
    assert.throws(() => run(bracesOnly(), entries), /exception/i);
  }
  assert.throws(() => evaluateAudit(bracesOnly(), lock, exceptions, new Date("2026-11-08")), /expired/i);
});

test("rejects_invalid_audit_output and inconsistent vulnerability totals", () => {
  for (const value of [{}, { ...recorded, error: { code: "E503" } }, { ...recorded, auditReportVersion: 99 }]) {
    assert.throws(() => run(value), /audit/i);
  }
  const report = bracesOnly();
  report.metadata.vulnerabilities.total = 0;
  assert.throws(() => run(report), /audit/i);
});

test("rejects incomplete advisory data and unresolved transitive findings", () => {
  for (const mutate of [
    (r) => { r.vulnerabilities.braces.via = []; },
    (r) => { r.vulnerabilities.braces.nodes = []; },
    (r) => { r.vulnerabilities.braces.via[0].severity = "unknown"; },
    (r) => { r.vulnerabilities.micromatch.via = ["missing-package"]; },
  ]) {
    const report = bracesOnly();
    mutate(report);
    assert.throws(() => run(report), /audit/i);
  }
});

test("rejects a cycle instead of silently discarding a path", () => {
  const tree = clone(lock);
  tree.packages["node_modules/braces"].dependencies["micromatch"] = "*";
  assert.throws(() => run(bracesOnly(), exceptions, tree), /cycle/i);
});

test("rejects a missing or malformed lockfile", () => {
  assert.throws(() => run(bracesOnly(), exceptions, {}), /lockfile/i);
  const tree = clone(lock);
  delete tree.packages["node_modules/braces"];
  assert.throws(() => run(bracesOnly(), exceptions, tree), /lockfile/i);
});

test("audit process failures cannot become a clean report", () => {
  for (const result of [
    { status: 0, stdout: "" },
    { status: 1, stdout: "not json" },
    { status: 2, stdout: JSON.stringify(recorded) },
    { status: null, signal: "SIGTERM", stdout: JSON.stringify(recorded) },
    { status: 0, error: new Error("spawn failed"), stdout: JSON.stringify(recorded) },
  ]) assert.throws(() => parseAuditResult(result), /audit/i);
  assert.deepEqual(parseAuditResult({ status: 1, stdout: JSON.stringify(recorded) }), recorded);
});

test("rejects a process exit code inconsistent with the report", () => {
  assert.throws(() => parseAuditResult({ status: 0, stdout: JSON.stringify(recorded) }), /audit/i);
  const report = bracesOnly();
  report.vulnerabilities = {};
  report.metadata.vulnerabilities = { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 };
  assert.throws(() => parseAuditResult({ status: 1, stdout: JSON.stringify(report) }), /audit/i);
  assert.deepEqual(parseAuditResult({ status: 0, stdout: JSON.stringify(report) }), report);
});
