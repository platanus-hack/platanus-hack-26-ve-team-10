import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone", // imagen mínima para Cloud Run
  serverExternalPackages: ["@google/adk"],
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
