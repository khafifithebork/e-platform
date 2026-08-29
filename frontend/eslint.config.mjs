import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",

    // The OpenNext build output (M13 T7). 25 MB of generated code, mostly
    // Next's own compiled runtime — linting it reported 9,518 problems in
    // code nobody here wrote, including errors, which would fail the build.
    //
    // Both are in `.gitignore` already, and eslint's flat config does not
    // read that file: ignoring for source control and ignoring for linting
    // are separate lists, and this is the second one.
    ".open-next/**",
    ".wrangler/**",
  ]),
]);

export default eslintConfig;
