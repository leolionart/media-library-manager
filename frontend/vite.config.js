import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  publicDir: false,
  define: {
    "process.env.NODE_ENV": JSON.stringify("production")
  },
  build: {
    outDir: resolve(__dirname, "../src/media_library_manager/static"),
    emptyOutDir: false,
    cssCodeSplit: false,
    modulePreload: false,
    sourcemap: false,
    lib: {
      entry: resolve(__dirname, "src/main.jsx"),
      formats: ["es"],
      fileName: () => "app.js",
      cssFileName: () => "styles.css"
    },
    rollupOptions: {
      output: {
        codeSplitting: false,
        entryFileNames: "app.js",
        chunkFileNames: "app.js",
        manualChunks: undefined,
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith(".css")) {
            return "styles.css";
          }
          return "[name][extname]";
        }
      }
    }
  }
});
