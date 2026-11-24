import type { NextConfig } from "next"

const config: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  // The console lives inside the NouGenShards monorepo; pin the root so Next
  // does not pick up the repo's top-level lockfiles.
  turbopack: { root: __dirname },
  outputFileTracingRoot: __dirname,
}

export default config
