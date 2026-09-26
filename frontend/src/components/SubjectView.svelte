<script lang="ts">
  import { onDestroy } from 'svelte'
  type S = { status?: string; phase?: string; instruction?: string; passage?: string; remaining_s?: number; question?: { id?: string; text?: string; number?: string }; card?: string; note?: string }
  let st = $state<S>({ status: 'idle' })
  let connected = $state(false)
  let ws: WebSocket | null = null
  let retry: number | null = null
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${proto}//${location.host}${location.pathname.replace(/\/$/, '')}/api/subject`)
    ws.onopen = () => (connected = true)
    ws.onmessage = (ev) => { try { const m = JSON.parse(ev.data); if (m.type === 'subject') st = m } catch { /* ignore */ } }
    ws.onclose = () => { connected = false; retry = window.setTimeout(connect, 1500) }
  }
  connect()
  onDestroy(() => { if (retry) clearTimeout(retry); ws?.close() })
  const lie = $derived((st.card ?? '').toLowerCase().includes('lie'))
</script>

<main class="subject" class:lie={Boolean(st.card) && lie} class:truth={Boolean(st.card) && !lie}>
  <div class="top"><span class="mark"></span><span class="eyebrow">subject screen</span><span class="dot" class:on={connected}></span></div>
  {#if st.status === 'calibrating'}
    <section class="center">
      <div class="eyebrow">calibration: {st.phase}{st.remaining_s != null ? `, ${Math.ceil(st.remaining_s)} s` : ''}</div>
      <p class="instr">{st.instruction}</p>
      {#if st.passage}<p class="passage">{st.passage}</p>{/if}
    </section>
  {:else if st.status === 'question' && st.question}
    <section class="center">
      <div class="eyebrow">question {st.question.number ?? ''}</div>
      <p class="q">{st.question.text}</p>
      {#if st.card}<div class="card"><span class="eyebrow">your instruction for this answer</span><b>{st.card}</b></div>{/if}
    </section>
  {:else if st.status === 'waiting'}
    <section class="center"><p class="instr muted">Thank you. Wait for the next question.</p></section>
  {:else if st.status === 'done'}
    <section class="center"><p class="instr">Finished. Thank you.</p></section>
  {:else}
    <section class="center"><p class="instr muted">{connected ? 'Waiting for the session to start.' : 'Connecting to the operator...'}</p></section>
  {/if}
  <footer class="muted">This screen shows instructions and questions only. It never shows measurements.</footer>
</main>

<style>
  .subject { min-height: 100vh; box-sizing: border-box; display: flex; flex-direction: column; padding: 20px 28px; background: var(--ground); color: var(--text); transition: background 0.3s; }
  .subject.truth { background: color-mix(in srgb, var(--ok) 10%, var(--ground)); }
  .subject.lie { background: color-mix(in srgb, var(--warn) 12%, var(--ground)); }
  .top { display: flex; align-items: center; gap: 10px; }
  .mark { width: 10px; height: 10px; border: 2px solid var(--accent); transform: rotate(45deg); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); margin-left: auto; }
  .dot.on { background: var(--ok); }
  .center { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 18px; max-width: 900px; margin: 0 auto; width: 100%; }
  .instr { font-size: 26px; line-height: 1.4; margin: 0; }
  .passage { font-size: 30px; line-height: 1.55; margin: 0; text-wrap: pretty; }
  .q { font-size: 40px; line-height: 1.3; margin: 0; font-weight: 500; text-wrap: balance; }
  .card { display: flex; flex-direction: column; gap: 6px; padding: 16px 20px; border: 1px solid var(--line-strong); background: var(--panel); }
  .card b { font-size: 28px; font-weight: 600; }
  .lie .card { border-color: var(--warn); } .lie .card b { color: var(--warn); }
  .truth .card { border-color: var(--ok); } .truth .card b { color: var(--ok); }
  .muted { color: var(--muted); }
  footer { font-size: 12px; text-align: center; }
  @media (max-width: 600px) { .q { font-size: 28px; } .passage { font-size: 22px; } .instr { font-size: 20px; } }
</style>
