import type { NextConfig } from "next";

const configuredDevOrigins = (process.env.NEXT_ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  poweredByHeader: false,
  output: "standalone",
  allowedDevOrigins: ["localhost", "127.0.0.1", ...configuredDevOrigins],
};

export default nextConfig;
