import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(import.meta.dirname, ".") },
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
