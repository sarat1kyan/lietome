# Lightman UI

Svelte 5 + Vite + TypeScript. Served by `lightman serve` from `src/lightman/api/static`.

```bash
npm install
npm run dev         # :5173, proxies /api to lightman serve on :8710
npm run check
npm run build       # -> ../src/lightman/api/static
npm run build:demo  # single HTML with demo-data.json inlined
```

Tokens: `src/styles.css`. Components: `src/components`. Data client: `src/lib/api.ts`.
Amber is reserved for evidence, blue for eyes/head, teal for voice. Numbers use JetBrains Mono.
