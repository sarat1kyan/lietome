<script lang="ts">
  import { onMount } from 'svelte'
  import { api } from './lib/api'
  import type { FeatureSeries, LmEvent, SessionDetail, SessionSummary } from './lib/types'
  import SessionRail from './components/SessionRail.svelte'
  import VideoStage from './components/VideoStage.svelte'
  import Timeline from './components/Timeline.svelte'
  import EventPanel from './components/EventPanel.svelte'
  import QualityStrip from './components/QualityStrip.svelte'

  let sessions = $state<SessionSummary[]>([])
  let current = $state<SessionSummary | null>(null)
  let detail = $state<SessionDetail | null>(null)
  let events = $state<LmEvent[]>([])
  let video = $state<FeatureSeries | null>(null)
  let audio = $state<FeatureSeries | null>(null)
  let selected = $state<LmEvent | null>(null)
  let playhead = $state(0) // microseconds
  let error = $state<string | null>(null)
  let loading = $state(false)

  const VIDEO_SIGNALS = ['head.yaw_deg', 'head.pitch_deg', 'eye.aspect_ratio_mean', 'blendshape.browDownLeft', 'blendshape.mouthPressLeft', 'blendshape.jawOpen', 'au.AU4', 'au.AU6', 'au.AU12', 'au.AU24']
  const AUDIO_SIGNALS = ['voice.f0_hz', 'voice.energy_db']

  async function open(s: SessionSummary) {
    loading = true; error = null; selected = null
    try {
      current = s
      const [d, ev, v] = await Promise.all([api.session(s.session_id), api.events(s.session_id), api.features(s.session_id, 'video', VIDEO_SIGNALS)])
      detail = d; events = ev; video = v
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

  onMount(async () => {
    try {
      sessions = await api.sessions()
      if (sessions.length) await open(sessions[0])
    } catch (e) { error = String(e) }
  })
</script>

<div class="app">
  <header class="top">
    <div class="brand">
      <span class="mark"></span>
      <span class="name">Lightman</span>
      <span class="eyebrow">behavioral analysis workstation</span>
    </div>
    <div class="top-right muted">
      {#if api.isDemo()}<span class="chip">demo data</span>{/if}
      <span>observations and interpretations of measured behavior. not a lie detector.</span>
    </div>
  </header>

  <SessionRail {sessions} current={current?.session_id ?? null} onselect={open} />

  <main class="stage">
    {#if error}<div class="error">{error}</div>{/if}
    {#if current && detail}
      <VideoStage session={current} {events} {selected} bind:playhead />
      <Timeline {events} {video} {audio} baseline={detail.baseline} audioBaseline={detail.audio_baseline}
                duration={current.duration_us ?? 0} bind:playhead {selected} onpick={pick} onseek={seekTo} />
      <QualityStrip {detail} {events} />
    {:else if !loading}
      <div class="empty">
        <p class="eyebrow">no sessions</p>
        <p>Run <code class="mono">lightman analyze video.mp4 -o output/</code> then reload, or drop a file on the rail.</p>
      </div>
    {/if}
  </main>

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
  .top { grid-area: top; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; border-bottom: 1px solid var(--line); background: var(--panel); }
  .brand { display: flex; align-items: baseline; gap: 12px; }
  .mark { width: 10px; height: 10px; background: var(--accent); display: inline-block; transform: translateY(1px); }
  .name { font-weight: 600; letter-spacing: 0.02em; font-size: 14px; }
  .top-right { display: flex; gap: 12px; align-items: center; font-size: 12px; }
  .chip { border: 1px solid var(--accent); color: var(--accent); padding: 1px 7px; border-radius: 10px; font-size: 11px; }
  .stage { grid-area: stage; display: grid; grid-template-rows: minmax(0, 1fr) auto auto; min-height: 0; background: var(--ground); }
  .empty { padding: 48px; color: var(--muted); }
  .error { margin: 12px; padding: 10px 12px; border: 1px solid var(--warn); color: var(--warn); border-radius: var(--radius); }
  code { background: var(--panel-2); padding: 1px 5px; border-radius: 3px; }
</style>
