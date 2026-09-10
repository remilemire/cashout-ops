import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // Same-origin API during dev; run the backend on :8000 (`make backend-dev`).
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../backend/static"),
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
  },
});
