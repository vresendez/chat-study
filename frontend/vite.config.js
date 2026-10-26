import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `npm run dev` serves on :5173 and proxies /api to the FastAPI backend.
// Prod: `npm run build` writes into ../static, which FastAPI serves.
const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8001";

export default defineConfig({
  plugins: [react()],
  server: { port: 3000, strictPort: true, proxy: { "/api": BACKEND } },
  build: { outDir: "../static", emptyOutDir: true },
});
