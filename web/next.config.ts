import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  output: "standalone",
  allowedDevOrigins: ["localhost", "127.0.0.1"],
};

export default nextConfig;
