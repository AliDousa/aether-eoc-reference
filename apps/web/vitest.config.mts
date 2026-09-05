import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// `.mts`, not `.ts`, on purpose: `@vitejs/plugin-react` is ESM-only, and a
// `.ts` config is loaded through a CommonJS path. On Node 22.12+ that happens
// to work because `require(esm)` is enabled by default, but relying on that
// interop hides the intent. An explicitly-ESM config states it.
//
// The package requires Node >= 22.12 for a related but separate reason: jsdom
// pulls an ESM-only encoding library through a CommonJS dependency, which only
// resolves once `require(esm)` exists. See the note in README quick start.
//
// `import.meta.dirname` would work on the supported range, but deriving the
// path from `import.meta.url` keeps this file portable to any Node 20+ runtime
// if the jsdom constraint is ever lifted.
const here = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": here },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.tsx"],
    // Inside the package root so bare imports resolve; see tests/web/README.md
    // at the repository root for why they are not under <repo>/tests/web.
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
