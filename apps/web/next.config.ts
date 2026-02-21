import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Next.js 16 uses Turbopack by default for dev and build
  // Output standalone for Docker deployments
  output: "standalone",
}

export default nextConfig
