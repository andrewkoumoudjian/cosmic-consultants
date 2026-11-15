import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  // The planner-v1 release lives in apps/atlas/public/data (same files, same hashes as the submitted planner).
  publicDir: '../atlas/public',
  esbuild: { jsx: 'automatic' },
  // .ts.net: lets the owner open the dev server over Tailscale by name.
  server: { port: 5181, fs: { allow: ['..'] }, allowedHosts: ['.ts.net'] },
  preview: { port: 5181 },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      // motion ships "use client" directives for RSC; they are meaningless in a static bundle.
      onwarn(warning, warn) {
        if (warning.code === 'MODULE_LEVEL_DIRECTIVE') return;
        warn(warning);
      },
    },
  },
});
