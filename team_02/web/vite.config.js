import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev server proxies /api to the FastAPI backend so the browser sees one origin
// (no CORS headaches during development). In production the frontend is built to
// static files and VITE_API_BASE points at the deployed API.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // framer-motion + Vite can pull in a second React copy → "Invalid hook call".
  // Dedupe so the app and framer-motion share one React.
  resolve: { dedupe: ["react", "react-dom"] },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
