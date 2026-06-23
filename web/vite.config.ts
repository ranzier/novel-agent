import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期：前端 :5173 调后端 :8000；交付期 build 成静态文件由 FastAPI 托管。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
