import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@pias/ui", "@pias/api-client", "@pias/permisos"],
};

export default nextConfig;
