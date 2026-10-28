import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  base: "/pyferro_admin/",
  plugins: [tailwindcss(), svelte()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
