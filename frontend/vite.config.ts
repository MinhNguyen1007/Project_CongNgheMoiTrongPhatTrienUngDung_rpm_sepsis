import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// WHY alias @: import từ pages/components ngắn hơn (`@/api/client`) thay vì
// `../../api/client`. Khớp với tsconfig paths.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
  },
});
