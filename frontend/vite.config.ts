import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser only ever talks to the Vite origin (localhost:5173). Vite
// forwards /api to Django, so the session and CSRF cookies are same-origin and
// no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        // Keep the browser's Host header (localhost:5173). Vite's string
        // shorthand sets changeOrigin: true, which rewrites Host to :8000;
        // Django's CSRF check then sees Origin :5173 != Host :8000 and
        // rejects every POST. With the Host kept, they match and Django
        // needs no CSRF_TRUSTED_ORIGINS exception.
        changeOrigin: false,
      },
    },
  },
});
