import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const routerPort = process.env.ROUTER_PORT || "8080";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": `http://127.0.0.1:${routerPort}`,
      "/health": `http://127.0.0.1:${routerPort}`,
      "/v1": `http://127.0.0.1:${routerPort}`,
    },
  },
});
