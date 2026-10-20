import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const script = fileURLToPath(new URL("./assert-bundle-budget.mjs", import.meta.url));
const presentScript = '<script src="/_next/static/chunks/present.js"></script>';

function runBudget(t, { html, assets = {} }) {
  const root = mkdtempSync(join(tmpdir(), "lingua-bundle-"));
  t.after(() => {
    // Only remove the fresh directory this test owns, never the build it checks.
    assert.equal(dirname(resolve(root)), resolve(tmpdir()));
    rmSync(root, { recursive: true, force: true });
  });
  const pages = join(root, ".next", "server", "app");
  mkdirSync(pages, { recursive: true });
  if (html !== null) writeFileSync(join(pages, "index.html"), html);
  for (const [name, content] of Object.entries(assets)) {
    const path = join(root, ".next", name);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, content);
  }
  const result = spawnSync(process.execPath, [script], {
    cwd: root,
    encoding: "utf8",
    timeout: 10_000,
    windowsHide: true,
  });
  assert.ifError(result.error);
  return result;
}

test("rejects_missing_local_script even when another script exists", (t) => {
  const result = runBudget(t, {
    html: `${presentScript}<script src="/_next/static/chunks/missing.js?v=1"></script>`,
    assets: { "static/chunks/present.js": "console.log('present');" },
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Missing local assets/);
  assert.match(result.stderr, /\/index.*\/_next\/static\/chunks\/missing\.js\?v=1/);
  assert.doesNotMatch(result.stdout, /budget met/);
});

for (const tag of [
  '<link rel="stylesheet" href="/_next/static/chunks/missing.css">',
  '<link href="/_next/static/chunks/missing.css" rel="stylesheet">',
]) {
  test(`rejects_missing_local_stylesheet: ${tag}`, (t) => {
    const result = runBudget(t, {
      html: `${presentScript}${tag}`,
      assets: { "static/chunks/present.js": "console.log('present');" },
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Missing local assets/);
    assert.match(result.stderr, /\/index.*\/_next\/static\/chunks\/missing\.css/);
    assert.doesNotMatch(result.stdout, /budget met/);
  });
}

test("accepts_complete_build and counts duplicate references once", (t) => {
  // One copy fits; two exceed the budget. Exercise real gzip and CLI counting.
  const content = `/*${randomBytes(200_000).toString("base64")}*/`;
  const css = "body { color: black; }";
  const ref = '<script src="/_next/static/chunks/present.js?v=1"></script>';
  const result = runBudget(t, {
    html: `${ref}${ref}
      <link rel="stylesheet" href="/_next/static/chunks/present.css">
      <link href="/_next/static/chunks/present.css" rel="stylesheet">
      <script src="https://example.test/external.js"></script>`,
    assets: {
      "static/chunks/present.js": content,
      "static/chunks/present.css": css,
    },
  });
  const total = gzipSync(content, { level: 9 }).length + gzipSync(css, { level: 9 }).length;
  assert.equal(result.status, 0, result.stderr);
  assert.ok(result.stdout.includes(`/index at ${(total / 1000).toFixed(1)} KB`));
  assert.match(result.stdout, /350\.0 KB ceiling/);
});

test("rejects_over_budget_build", (t) => {
  const result = runBudget(t, {
    html: presentScript,
    assets: { "static/chunks/present.js": `/*${randomBytes(400_000).toString("base64")}*/` },
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Routes over the 350\.0 KB/);
  assert.match(result.stderr, /\/index/);
});

test("rejects_empty_page_list", (t) => {
  const result = runBudget(t, { html: null });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /No built pages found/);
});

test("rejects_page_with_no_resolvable_assets", (t) => {
  const result = runBudget(t, {
    html: '<script src="https://example.test/external.js"></script>',
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /assets could not be resolved at all/);
});
