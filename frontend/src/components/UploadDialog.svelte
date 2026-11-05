<script lang="ts">
  import { api } from '../lib/api'
  import ConsentDialog from './ConsentDialog.svelte'
  import type { Consent } from '../lib/types'
  let { onclose, ondone }: { onclose: () => void; ondone: (sessionId: string) => void } = $props()
  let file = $state<File | null>(null)
  let stage = $state<'pick' | 'consent' | 'running' | 'error'>('pick')
  let message = $state('')
  let dragging = $state(false)
  function pick(f: File | null | undefined) { if (f) { file = f; stage = 'consent' } }
  async function onConsent(code: string, consent: Consent) {
    if (!file) return
    stage = 'running'; message = 'Uploading...'
    try {
      const jid = await api.analyze(file, code, consent, true)
      message = 'Analysing. Long recordings take a while; you can keep this open.'
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500))
        const j = await api.job(jid)
        if (j.state === 'done' && j.session_id) { ondone(j.session_id); return }
        if (j.state === 'failed') { stage = 'error'; message = j.error ?? 'analysis failed'; return }
      }
    } catch (e) { stage = 'error'; message = String(e) }
  }
</script>

{#if stage === 'consent'}
  <ConsentDialog wantAudio={true} wantRecording={false} onconfirm={onConsent} oncancel={onclose} />
{:else}
<div class="backdrop" role="presentation">
  <div class="card" role="dialog" aria-modal="true" aria-labelledby="up-title">
    <h2 id="up-title">Analyse a recording</h2>
    {#if stage === 'pick'}
      <label class="drop" class:on={dragging} ondragover={(e) => { e.preventDefault(); dragging = true }} ondragleave={() => (dragging = false)} ondrop={(e) => { e.preventDefault(); dragging = false; pick(e.dataTransfer?.files?.[0]) }}>
        <input type="file" accept="video/*" onchange={(e) => pick((e.currentTarget as HTMLInputElement).files?.[0])} />
        <span class="big">Drop a video here, or click to choose one</span>
        <span class="muted">One face in view works best. The file is analysed on this machine and not kept unless you choose to.</span>
      </label>
    {:else}
      <p class:err={stage === 'error'}>{message}</p>
      {#if stage === 'running'}<div class="bar"><i></i></div>{/if}
    {/if}
    <div class="actions"><button onclick={onclose}>{stage === 'running' ? 'Hide' : 'Close'}</button></div>
  </div>
</div>
{/if}

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(5, 7, 10, 0.72); display: grid; place-items: center; z-index: 50; padding: 16px; }
  .card { width: min(520px, 100%); background: var(--panel); border: 1px solid var(--line-strong); border-radius: 6px; padding: 22px 24px; display: flex; flex-direction: column; gap: 14px; }
  h2 { margin: 0; font-size: 18px; font-weight: 600; }
  .drop { display: flex; flex-direction: column; gap: 6px; align-items: center; text-align: center; padding: 34px 18px; border: 1px dashed var(--line-strong); border-radius: 6px; cursor: pointer; }
  .drop.on, .drop:hover { border-color: var(--accent); background: var(--accent-soft); }
  .drop input { display: none; }
  .big { font-size: 15px; }
  .muted { font-size: 12.5px; color: var(--muted); max-width: 44ch; }
  .err { color: var(--warn); }
  .bar { height: 4px; background: var(--line); overflow: hidden; border-radius: 2px; }
  .bar i { display: block; height: 100%; width: 30%; background: var(--accent); animation: slide 1.4s infinite ease-in-out; }
  @keyframes slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(340%); } }
  @media (prefers-reduced-motion: reduce) { .bar i { animation: none; width: 100%; opacity: 0.5; } }
  .actions { display: flex; justify-content: flex-end; }
</style>
