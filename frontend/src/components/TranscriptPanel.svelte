<script lang="ts">
  import { onDestroy } from 'svelte'
  import { api, tc } from '../lib/api'
  let { sessionId, playhead, onseek }: { sessionId: string; playhead: number; onseek: (us: number) => void } = $props()
  let doc = $state<any>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  function load(id: string) {
    api.transcript(id).then((d) => {
      if (id !== sessionId) return
      doc = d
      if (d?.status === 'pending') timer = setTimeout(() => load(id), 3000)
    }).catch(() => (doc = null))
  }
  $effect(() => { const id = sessionId; if (timer) clearTimeout(timer); doc = null; load(id) })
  onDestroy(() => { if (timer) clearTimeout(timer) })
  const words = $derived((doc?.words ?? []) as { start_us: number; end_us: number; word: string; prob: number }[])
  const markAt = $derived.by(() => {
    const m = new Map<number, string>()
    for (const k of (doc?.markers ?? []) as any[]) {
      const n = k.phrase.split(' ').length
      for (let i = 0; i < n; i++) m.set(k.word_index + i, k.kind)
    }
    return m
  })
  const current = $derived(words.findIndex((w) => w.start_us <= playhead && playhead < w.end_us + 150_000))
  const hedges = $derived(((doc?.markers ?? []) as any[]).filter((m) => m.kind === 'hedge').length)
  const denials = $derived(((doc?.markers ?? []) as any[]).filter((m) => m.kind === 'denial').length)
</script>

{#if doc && doc.status !== 'none'}
<section class="tr">
  <div class="hdr">
    <span class="eyebrow">transcript</span>
    {#if doc.status === 'pending'}<span class="muted">transcribing on this machine...</span>
    {:else if doc.status === 'done'}<span class="muted mono">{words.length} words, {doc.language ?? '?'}{doc.marking ? `, ${doc.marking}` : ''}; <b class="hedge">{hedges} hedges</b>, <b class="denial">{denials} denials</b>, {doc.denial_moments?.length ?? 0} denials with a face or body change within 1 s</span>
    {:else}<span class="muted">{doc.reason ?? doc.status}</span>{/if}
  </div>
  {#if doc.status === 'done'}
    <p class="words">
      {#each words as w, i (i)}<button class="w" class:cur={i === current} class:hedge={markAt.get(i) === 'hedge'} class:denial={markAt.get(i) === 'denial'} onclick={() => onseek(w.start_us)} title={`${tc(w.start_us).slice(3)} p=${w.prob}`}>{w.word}</button>{' '}{/each}
    </p>
    {#if doc.denial_moments?.length}
      <div class="moments">
        {#each doc.denial_moments as d (d.start_us)}
          <button class="dm" onclick={() => onseek(d.start_us)}><span class="mono">{tc(d.start_us).slice(3)}</span> <b class="denial">"{d.phrase}"</b> with {d.events.map((e: any) => e.label.replace(/^(brief |microexpression candidate: )?expression pattern: /, '')).join('; ')}</button>
        {/each}
      </div>
    {/if}
    <p class="muted note">Hedges and denials come from small English word lists. Verbal cues are as weak as nonverbal ones in the research; the timing of a denial against a face change is what is worth replaying.</p>
  {/if}
</section>
{/if}

<style>
  .tr { border-top: 1px solid var(--line); background: var(--panel); padding: 10px 16px 12px; }
  .hdr { display: flex; gap: 12px; align-items: baseline; font-size: 11.5px; flex-wrap: wrap; }
  .words { font-size: 14px; line-height: 1.8; margin: 8px 0; max-height: 180px; overflow-y: auto; }
  .w { background: none; border: 0; padding: 0 1px; color: var(--text); font: inherit; cursor: pointer; border-radius: 2px; }
  .w:hover { background: var(--panel-2); }
  .w.cur { background: var(--accent-soft); outline: 1px solid var(--accent); }
  .w.hedge, b.hedge { color: var(--accent); }
  .w.denial, b.denial { color: var(--warn); }
  b { font-weight: 500; }
  .moments { display: flex; flex-direction: column; gap: 3px; margin: 4px 0; }
  .dm { text-align: left; background: var(--panel-2); border: 1px solid var(--line); border-radius: var(--radius); padding: 4px 8px; font-size: 12px; color: var(--muted); cursor: pointer; }
  .dm:hover { border-color: var(--line-strong); }
  .note { font-size: 11px; margin: 6px 0 0; max-width: 90ch; }
</style>
