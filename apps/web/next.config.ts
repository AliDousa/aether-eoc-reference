import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emits a self-contained server bundle so the Docker image does not need to
  // ship node_modules. See apps/web/Dockerfile.
  output: "standalone",
  typedRoutes: true,
  // Next 16 writes AGENTS.md / CLAUDE.md into the app directory by default.
  // This repository ships only files it authored, so that is turned off.
  agentRules: false,
};

export default nextConfig;
