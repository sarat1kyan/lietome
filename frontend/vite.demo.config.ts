import { readFileSync } from 'node:fs'
import { defineConfig, type Plugin } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { viteSingleFile } from 'vite-plugin-singlefile'

// Demo build: one self-contained HTML file with a session inlined (see
// experiments/build_demo_bundle.py). No server, no fetch; fonts still come from Google Fonts.
function inlineDemoData(): Plugin {
  return {
    name: 'lightman-inline-demo-data',
    transformIndexHtml(html) {
      const data = readFileSync('demo-data.json', 'utf-8')
      return html.replace('<div id="app"></div>', `<script>window.__LIGHTMAN_DEMO__=${data}</script>\n    <div id="app"></div>`)
    },
  }
}

export default defineConfig({
  plugins: [svelte(), inlineDemoData(), viteSingleFile()],
  base: './',
  build: { outDir: 'dist-demo', emptyOutDir: true },
})
