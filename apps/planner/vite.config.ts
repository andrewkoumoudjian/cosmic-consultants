import { defineConfig } from "vite";

// ADR-0012: one data release for both apps. The hashed planner-v1 files live in
// apps/atlas/public/data/planner-v1 (written by `python -m planner.release`).
export default defineConfig({
  base: "./",
  publicDir: "../atlas/public",
  esbuild: { jsx: "automatic" },
  server: { port: 5174, fs: { allow: [".."] } },
  build: {
    target: "es2022",
    // The globe chunk (three.js) is ~1.9 MB and only loads on step 4.
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      // Motion ships "use client" directives for React Server Components; they mean nothing in this SPA.
      onwarn(warning, warn) {
        if (warning.code === "MODULE_LEVEL_DIRECTIVE") return;
        warn(warning);
      },
    },
  },
});
