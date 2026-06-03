import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          arco: ["@arco-design/web-react"],
          charts: ["echarts", "echarts-for-react"],
          graph: ["@antv/g6"],
        },
      },
    },
  },
});
