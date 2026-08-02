import type { NextConfig } from "next";

const apiProxy = process.env.SHORTLISTR_API_PROXY ?? "http://127.0.0.1:8787";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxy}/:path*`,
      },
    ];
  },
};

export default nextConfig;
