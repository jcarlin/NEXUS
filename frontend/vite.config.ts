import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import path from "path";

export default defineConfig({
  plugins: [
    TanStackRouterVite(),
    react(),
    tailwindcss(),
    ...(process.env.ANALYZE
      ? [(await import("rollup-plugin-visualizer")).visualizer({ open: true, gzipSize: true })]
      : []),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-router": ["@tanstack/react-router", "@tanstack/react-query"],
          "vendor-pdf": ["react-pdf"],
          "vendor-markdown": ["react-markdown", "react-syntax-highlighter", "remark-gfm"],
          "vendor-uppy": [
            "@uppy/core", "@uppy/dashboard", "@uppy/drag-drop",
            "@uppy/file-input", "@uppy/progress-bar", "@uppy/react",
            "@uppy/status-bar", "@uppy/xhr-upload",
          ],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    css: true,
    exclude: ["e2e/**", "node_modules/**"],
  },
});
