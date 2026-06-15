import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Standalone empacota um servidor Node minimo para a imagem de producao.
  output: "standalone",
  // Sem source maps no cliente: nao expor o mapa de volta ao codigo-fonte.
  productionBrowserSourceMaps: false,
  // Pin the workspace root to this app (multiple lockfiles exist higher up).
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
