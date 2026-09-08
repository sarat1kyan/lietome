<script lang="ts">
  import { onMount } from 'svelte'
  import { api } from './lib/api'
  import type { FeatureSeries, LmEvent, SessionDetail, SessionSummary } from './lib/types'
  import SessionRail from './components/SessionRail.svelte'
  import VideoStage from './components/VideoStage.svelte'
  import Timeline from './components/Timeline.svelte'
  import EventPanel from './components/EventPanel.svelte'
  import QualityStrip from './components/QualityStrip.svelte'
  import LiveView from './components/LiveView.svelte'
  import SummaryCard from './components/SummaryCard.svelte'
  import ProtocolTable from './components/ProtocolTable.svelte'
  import FramePanel from './components/FramePanel.svelte'

  let sessions = $state<SessionSummary[]>([])
  let current = $state<SessionSummary | null>(null)
  let detail = $state<SessionDetail | null>(null)
  let events = $state<LmEvent[]>([])
  let video = $state<FeatureSeries | null>(null)
  let audio = $state<FeatureSeries | null>(null)
  let protocol = $state<any>(null)
  let selected = $state<LmEvent | null>(null)
  let playhead = $state(0) // microseconds
  let error = $state<string | null>(null)
  let loading = $state(false)
  let view = $state<'sessions' | 'live'>('sessions')

  const VIDEO_SIGNALS = ['head.yaw_deg', 'head.pitch_deg', 'eye.aspect_ratio_mean', 'blendshape.browDownLeft', 'blendshape.mouthPressLeft', 'blendshape.jawOpen', 'au.AU4', 'au.AU6', 'au.AU12', 'au.AU24']
  const AUDIO_SIGNALS = ['voice.f0_hz', 'voice.energy_db']

  async function open(s: SessionSummary) {
    loading = true; error = null; selected = null
    try {
      current = s
      const [d, ev, v] = await Promise.all([api.session(s.session_id), api.events(s.session_id), api.features(s.session_id, 'video', VIDEO_SIGNALS)])
      detail = d; events = ev; video = v
      protocol = await api.protocol(s.session_id)
      audio = s.has_audio ? await api.features(s.session_id, 'audio', AUDIO_SIGNALS) : null
      playhead = 0
    } catch (e) {
      error = String(e)
    } finally {
      loading = false
    }
  }

  function seekTo(us: number) { playhead = us }
  function pick(e: LmEvent) { selected = e; playhead = e.peak_us ?? e.start_us }

  async function reload(selectId?: string) {
    sessions = await api.sessions()
    const target = selectId ? sessions.find((s) => s.session_id === selectId) : sessions[0]
    if (target) await open(target)
  }
  async function liveDone(sessionId: string) {
    view = 'sessions'
    try { await reload(sessionId) } catch (e) { error = String(e) }
  }

  function onKey(ev: KeyboardEvent) {
    if (view !== 'sessions' || !current) return
    const tag = (ev.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
    const list = events.filter((e) => e.event_type !== 'blink').sort((a, b) => a.start_us - b.start_us)
    if (ev.key === 'ArrowRight') { playhead = Math.min((current.duration_us ?? playhead + 1e6), playhead + (ev.shiftKey ? 5e6 : 1e6)); ev.preventDefault() }
    else if (ev.key === 'ArrowLeft') { playhead = Math.max(0, playhead - (ev.shiftKey ? 5e6 : 1e6)); ev.preventDefault() }
    else if (ev.key === 'j' || ev.key === 'k') {
      const i = selected ? list.findIndex((e) => e.event_id === selected!.event_id) : -1
      const next = ev.key === 'j' ? list[i + 1] : list[Math.max(0, i - 1)]
      if (next) pick(next)
    } else if (ev.key === 'Escape') selected = null
  }

  onMount(async () => {
    window.addEventListener('keydown', onKey)
    try { await reload() } catch (e) { error = String(e) }
    return () => window.removeEventListener('keydown', onKey)
  })
</script>

<div class="app">
  <header class="top">
    <div class="brand-nav">
    <div class="brand">
      <span class="mark"></span>
      <span class="name">Lightman</span>
      <span class="eyebrow">behavioral analysis workstation</span>
    </div>
    <nav class="nav">
      <button class:on={view === 'sessions'} onclick={() => (view = 'sessions')}>sessions</button>
      <button class:on={view === 'live'} onclick={() => (view = 'live')} disabled={api.isDemo()} title={api.isDemo() ? 'needs lightman serve' : ''}>live</button>
    </nav>
    </div>
    <div class="top-right muted">
      {#if api.isDemo()}<span class="chip">demo data</span>{/if}
      <span class="keys mono" title="keyboard">arrows seek, shift+arrows 5 s, j/k next/prev event, esc clear</span>
      <span>observations and interpretations of measured behavior. not a lie detector.</span>
    </div>
  </header>

  <SessionRail {sessions} current={current?.session_id ?? null} onselect={open} />

  {#if view === 'live'}
    <LiveView ondone={liveDone} />
  {:else}
  <main class="stage">
    {#if error}<div class="error">{error}</div>{/if}
    {#if current && detail}
      <VideoStage session={current} {events} {selected} bind:playhead />
      <FramePanel sessionId={current.session_id} {playhead} />
      <Timeline {events} {video} {audio} {protocol} baseline={detail.baseline} audioBaseline={detail.audio_baseline}
                duration={current.duration_us ?? 0} bind:playhead {selected} onpick={pick} onseek={seekTo} />
      <ProtocolTable {protocol} onseek={seekTo} />
      <SummaryCard {detail} {events} />
      <QualityStrip {detail} {events} />
    {:else if !loading}
      <div class="empty">
        <p class="eyebrow">no sessions</p>
        <p>Run <code class="mono">lightman analyze video.mp4 -o output/</code> then reload, or drop a file on the rail.</p>
      </div>
    {/if}
  </main>
  {/if}

  <EventPanel {selected} {events} session={current} baseline={detail?.baseline ?? null} onpick={pick} />
</div>

<style>
  .app {
    display: grid;
    grid-template-columns: 232px minmax(0, 1fr) 340px;
    grid-template-rows: 44px minmax(0, 1fr);
    grid-template-areas: "top top top" "rail stage panel";
    height: 100vh;
  }
  .brand-nav { display: flex; align-items: center; }
  .top { grid-area: top; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; border-bottom: 1px solid var(--line); background: var(--panel); }
  .brand { display: flex; align-items: baseline; gap: 12px; }
  .nav { display: flex; gap: 4px; margin-left: 24px; }
  .nav button { background: none; border-color: transparent; color: var(--muted); padding: 4px 10px; }
  .nav button.on { color: var(--text); border-color: var(--line-strong); background: var(--panel-2); }
  .nav button:disabled { opacity: 0.4; cursor: default; }
  .mark { width: 10px; height: 10px; background: var(--accent); display: inline-block; transform: translateY(1px); }
  .name { font-weight: 600; letter-spacing: 0.02em; font-size: 14px; }
  .top-right { display: flex; gap: 12px; align-items: center; font-size: 12px; }
  .keys { font-size: 10.5px; color: var(--faint); }
  .chip { border: 1px solid var(--accent); color: var(--accent); padding: 1px 7px; border-radius: 10px; font-size: 11px; }
  .stage { grid-area: stage; display: grid; grid-template-rows: minmax(0, 1fr) auto auto auto auto; min-height: 0; background: var(--ground); overflow-y: auto; }
  .empty { padding: 48px; color: var(--muted); }
  .error { margin: 12px; padding: 10px 12px; border: 1px solid var(--warn); color: var(--warn); border-radius: var(--radius); }
  code { background: var(--panel-2); padding: 1px 5px; border-radius: 3px; }
</style>
