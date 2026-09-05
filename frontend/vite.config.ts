import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Build output lands inside the Python package so `lightman serve` can host it.
export default defineConfig({
  plugins: [svelte()],
  base: './',
  build: { outDir: '../src/lightman/api/static', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8710' } },
})
