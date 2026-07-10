import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

const routerPort = process.env.ROUTER_PORT || "9456";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  build: {
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["echarts"],
          vue: ["@vueuse/core", "pinia", "vue", "vue-router"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": `http://127.0.0.1:${routerPort}`,
      "/health": `http://127.0.0.1:${routerPort}`,
      "/v1": `http://127.0.0.1:${routerPort}`,
    },
  },
});
