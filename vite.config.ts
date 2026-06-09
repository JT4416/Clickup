import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Renderer build. The Electron main process is compiled separately
// via tsconfig.electron.json into dist-electron/.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
