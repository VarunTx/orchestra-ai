import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  turbopack: { root: process.cwd() },
  poweredByHeader: false,
};
export default config;
