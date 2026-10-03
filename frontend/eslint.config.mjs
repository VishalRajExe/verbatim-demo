import { defineConfig } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // The migrated Verbatim UI relies on two React Compiler-era rules that were
    // authored before those rules existed: fetching effects reset state before an
    // async body (set-state-in-effect) and SWR refs read during render (refs).
    // Rewriting that logic risks regressions, so these stay advisory (warn) while
    // every correctness rule remains an error.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
    },
  },
  {
    // Vendored/minified assets (e.g. public/pdfjs/pdf.worker.min.mjs) and build
    // output are not project source and must not be linted.
    ignores: [".next/**", "out/**", "node_modules/**", "next-env.d.ts", "public/**"],
  },
]);

export default eslintConfig;
