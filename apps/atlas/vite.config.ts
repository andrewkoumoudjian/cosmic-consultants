import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { defineConfig, type Plugin } from "vite";

const require = createRequire(import.meta.url);

/**
 * MapLibre GL JS v6 runs the map in a web worker and looks for
 * `maplibre-gl-worker.mjs` next to the bundle it was loaded from. A bundled
 * app breaks that lookup, so we serve the worker file ourselves: from
 * node_modules during dev, and as a static asset in the build output.
 */
function maplibreWorker(): Plugin {
  const workerFile = require.resolve("maplibre-gl/dist/maplibre-gl-worker.mjs");
  return {
    name: "maplibre-gl-worker",
    configureServer(server) {
      server.middlewares.use("/maplibre-gl-worker.mjs", (_request, response) => {
        response.setHeader("Content-Type", "text/javascript");
        response.end(readFileSync(workerFile));
      });
    },
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "maplibre-gl-worker.mjs",
        source: readFileSync(workerFile),
      });
    },
  };
}

// Static build only. The atlas is a plain static site (Cloudflare Pages in ADR-0003).
// No API keys: the NASA GIBS basemap and the mock data are public.
export default defineConfig({
  base: "./",
  plugins: [maplibreWorker()],
  build: {
    outDir: "dist",
    rollupOptions: { input: { main: "index.html", planner: "planner.html" } },
    sourcemap: true,
    target: "es2022",
  },
  server: {
    port: 5173,
  },
});
