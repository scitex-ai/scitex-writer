import { fileURLToPath } from "url";
import { resolve } from "path";
import { defineConfig } from "vite";

const __dirname = fileURLToPath(new URL(".", import.meta.url));

// @scitex/sdk component imports use its package exports in both tsc and Vite.
// The npm file dependency can target a checkout or get_frontend_package_dir()
// from an installed wheel; it must be regenerated for the active environment.
export default defineConfig({
  base: "/static/writer/",
  resolve: {
    alias: {
      // Pin SDK UI's `monaco-editor` peer import to writer's own copy.
      "monaco-editor": resolve(__dirname, "node_modules/monaco-editor"),
    },
    preserveSymlinks: true,
  },
  build: {
    outDir: "../static/writer",
    emptyOutDir: false,
    sourcemap: true,
    // Templates already load one shared stylesheet at this stable URL.
    // Splitting vendor JavaScript must not strand its extracted styles.
    cssCodeSplit: false,
    manifest: true,
    rollupOptions: {
      input: {
        index: "src/index.ts",
        viewer: "src/viewer.ts",
      },
      output: {
        // Monaco's complete sources exceed the repository's per-file guard
        // in one map. Keep its foundational utilities separate from editor
        // modules while retaining every source and the existing entry URLs.
        onlyExplicitManualChunks: true,
        manualChunks(id) {
          if (id.includes("/monaco-editor/esm/vs/base/"))
            return "monaco-base";
        },
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: (asset) =>
          asset.name === "style.css"
            ? "assets/index.css"
            : "assets/[name][extname]",
      },
    },
  },
});
