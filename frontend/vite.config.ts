import { defineConfig } from "vite";

const proxyTarget = process.env.VITE_PROXY_TARGET ?? "http://localhost:8200";

export default defineConfig({
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      "/v1": {
        target: proxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
