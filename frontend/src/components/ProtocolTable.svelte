<script lang="ts">
  import { tc } from '../lib/api'
  let { protocol, onseek }: { protocol: any; onseek: (us: number) => void } = $props()
  const qs = $derived((protocol?.questions ?? []) as any[])
  const cvr = $derived(protocol?.control_vs_relevant ?? {})
  const gt = $derived(protocol?.ground_truth ?? {})
  const notes = $derived((protocol?.notes ?? []) as string[])
  const poss = $derived(protocol?.possibility ?? null)
  const idxColor = (v: number | null) => (v == null ? 'var(--muted)' : v < 40 ? 'var(--cool)' : v < 55 ? 'var(--muted)' : v < 70 ? 'var(--accent)' : 'var(--warn)')
  const f = (v: number | null | undefined, d = 0) => (v == null ? '-' : v.toFixed(d))
</script>

{#if qs.length}
<section class="proto">
  <div class="hdr"><span class="eyebrow">interview protocol</span><span class="muted">click a row to seek</span></div>
  <div class="wrap">
  <table class="mono">
    <thead><tr><th>#</th><th>cat</th><th class="txt">question</th><th>asked</th><th>latency</th><th>speech</th><th>dev/min</th><th>max SD</th><th>episodes</th><th>blink/min</th><th>pitch SD</th><th class="txt">signals</th><th class="txt">expressions</th><th>cues</th><th>index</th></tr></thead>
    <tbody>
      {#each qs as q (q.id)}
        <tr class:rel={q.category === 'relevant'} class:ctl={q.category === 'control'} onclick={() => onseek(q.start_us)}>
          <td>{q.id}</td><td>{q.category[0].toUpperCase()}</td><td class="txt sans">{q.text}{#if q.expected} <em class="tag">{q.expected}</em>{/if}</td>
          <td>{tc(q.start_us).slice(3)}</td><td>{q.response_latency_ms == null ? '-' : f(q.response_latency_ms) + ' ms'}</td>
          <td>{f(q.answer_speech_s, 1)} s</td><td>{f(q.deviations_per_min, 1)}</td><td>{f(q.max_severity, 1)}</td><td>{q.episodes}</td>
          <td>{f(q.blink_rate_per_min)}</td><td>{q.voice_pitch_delta_sd == null ? '-' : (q.voice_pitch_delta_sd >= 0 ? '+' : '') + f(q.voice_pitch_delta_sd, 1)}</td>
          <td class="txt">{q.top_signals.map((t: any) => `${t.feature.replace(/^(blendshape|au)\./, '')} x${t.count}`).join(', ')}</td>
          <td class="txt sans expr">{(q.expression_patterns ?? []).join(', ') || '-'}</td>
          <td title={q.cues ? q.cues.cues.filter((c: any) => c.present).map((c: any) => c.name).join(', ') || 'none present' : ''}>{q.cues ? `${q.cues.present}/${q.cues.evaluated}` : '-'}</td>
          <td title={q.cue_index?.text ?? ''} style:color={idxColor(q.cue_index?.value ?? null)}>{q.cue_index?.value != null ? `${Math.round(q.cue_index.value)} ${q.cue_index.band}` : '-'}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  </div>
  <div class="cmp">
    {#if poss?.text}
      <span class="poss"><b>possibility of deception, cue-based:</b> {poss.text}</span>
    {/if}
    {#if cvr.delta_deviations_per_min != null}
      <span>relevant minus control: <b class="mono">{cvr.delta_deviations_per_min >= 0 ? '+' : ''}{f(cvr.delta_deviations_per_min, 1)}</b> dev/min{#if cvr.delta_latency_ms != null}, <b class="mono">{cvr.delta_latency_ms >= 0 ? '+' : ''}{f(cvr.delta_latency_ms)}</b> ms latency{/if}{#if cvr.permutation_p_deviations != null}, permutation p <b class="mono">{f(cvr.permutation_p_deviations, 2)}</b>{/if} (n {cvr.n_control} control, {cvr.n_relevant} relevant)</span>
    {/if}
    {#if gt.auroc != null}
      <span>expected-class discrimination: AUROC <b class="mono">{f(gt.auroc, 2)}</b> over {gt.n_truth} truth / {gt.n_lie} lie items (0.5 = chance). experimental, one person, one session.</span>
    {/if}
    {#each notes as n}<span class="note">{n}</span>{/each}
    <span class="muted">question type, length and order move every number here. nothing on this table identifies a lie.</span>
  </div>
</section>
{/if}

<style>
  .proto { border-top: 1px solid var(--line); background: var(--panel); padding: 10px 16px; }
  .hdr { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 12px; }
  .wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 11.5px; }
  th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  th { color: var(--muted); font-weight: normal; letter-spacing: 0.08em; text-transform: uppercase; font-size: 10px; }
  td.txt, th.txt { white-space: normal; min-width: 180px; }
  .sans { font-family: var(--font-ui); }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--panel-2); }
  tr.rel td:first-child { border-left: 2px solid var(--accent); }
  tr.ctl td:first-child { border-left: 2px solid var(--cool); }
  .expr { color: var(--violet); }
  .tag { font-style: normal; color: var(--muted); font-size: 10.5px; border: 1px solid var(--line-strong); padding: 0 4px; border-radius: 2px; }
  .cmp { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; font-size: 12px; }
  .poss { padding: 8px 10px; background: var(--panel-2); border-left: 2px solid var(--accent); max-width: 90ch; line-height: 1.45; }
  .poss b { color: var(--accent); font-weight: 500; }
  .note { color: var(--accent); }
</style>
