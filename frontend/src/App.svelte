<script lang="ts">
  import { onMount } from 'svelte'
  import { api } from './lib/api'
  import type { FeatureSeries, LmEvent, PulseSeries, Range, SessionDetail, SessionSummary } from './lib/types'
  import SessionRail from './components/SessionRail.svelte'
  import VideoStage from './components/VideoStage.svelte'
  import Timeline from './components/Timeline.svelte'
  import EventPanel from './components/EventPanel.svelte'
  import QualityStrip from './components/QualityStrip.svelte'
  import LiveView from './components/LiveView.svelte'
  import SummaryCard from './components/SummaryCard.svelte'
  import ProtocolTable from './components/ProtocolTable.svelte'
  import FramePanel from './components/FramePanel.svelte'
  import KeyMoments from './components/KeyMoments.svelte'
  import ComparePanel from './components/ComparePanel.svelte'
  import HistoryCard from './components/HistoryCard.svelte'
  import TranscriptPanel from './components/TranscriptPanel.svelte'
  import NotesPanel from './components/NotesPanel.svelte'
  import PracticeCard from './components/PracticeCard.svelte'
  import ClientsView from './components/ClientsView.svelte'
  import SubjectView from './components/SubjectView.svelte'
  import HomeView from './components/HomeView.svelte'
  import SettingsView from './components/SettingsView.svelte'
  import Onboarding from './components/Onboarding.svelte'
  import UploadDialog from './components/UploadDialog.svelte'
  import { app, loadSettings, research } from './lib/settings.svelte'
  const subjectMode = typeof location !== 'undefined' && location.hash === '#subject'

  let sessions = $state<SessionSummary[]>([])
  let current = $state<SessionSummary | null>(null)
  let detail = $state<SessionDetail | null>(null)
  let events = $state<LmEvent[]>([])
  let video = $state<FeatureSeries | null>(null)
  let audio = $state<FeatureSeries | null>(null)
  let pulse = $state<PulseSeries | null>(null)
  let protocol = $state<any>(null)
  let selected = $state<LmEvent | null>(null)
  let playhead = $state(0) // microseconds
  let error = $state<string | null>(null)
  let loading = $state(false)
  let view = $state<'home' | 'sessions' | 'live' | 'clients' | 'settings'>('home')
  let tab = $state<'overview' | 'review' | 'conversation' | 'research'>('overview')
  let uploading = $state(false)
  let onboarding = $state(false)
  let compare = $state<{ a: Range | null; b: Range | null } | null>(null)
  function setRange(which: 'a' | 'b', r: Range) { compare = { a: which === 'a' ? r : compare?.a ?? null, b: which === 'b' ? r : which === 'a' ? null : compare?.b ?? null } }

  const VIDEO_SIGNALS = ['head.yaw_deg', 'head.pitch_deg', 'eye.aspect_ratio_mean', 'blendshape.browDownLeft', 'blendshape.mouthPressLeft', 'blendshape.jawOpen', 'au.AU4', 'au.AU6', 'au.AU12', 'au.AU24']
  const AUDIO_SIGNALS = ['voice.f0_hz', 'voice.energy_db', 'voice.rate_syl_s']

  async function open(s: SessionSummary) {
    loading = true; error = null; selected = null
    try {
      current = s
      const [d, ev, v] = await Promise.all([api.session(s.session_id), api.events(s.session_id), api.features(s.session_id, 'video', VIDEO_SIGNALS)])
      detail = d; events = ev; video = v
      protocol = await api.protocol(s.session_id)
      audio = s.has_audio ? await api.features(s.session_id, 'audio', AUDIO_SIGNALS) : null
      pulse = await api.pulse(s.session_id).catch(() => null)
      playhead = 0; compare = null
      if (tab === 'research' && !research()) tab = 'overview'
    } catch (e) {
      error = String(e)
    } finally {
      loading = false
    }
  }

  function seekTo(us: number) { playhead = us }
  function pick(e: LmEvent) { selected = e; playhead = e.peak_us ?? e.start_us; if (tab !== 'review') tab = 'review' }

  async function reload(selectId?: string) {
    sessions = await api.sessions()
    const target = selectId ? sessions.find((s) => s.session_id === selectId) : sessions[0]
    if (target) await open(target)
  }
  async function liveDone(sessionId: string) {
    view = 'sessions'; tab = 'overview'
    try { await reload(sessionId) } catch (e) { error = String(e) }
  }
  async function openSession(s: SessionSummary) { view = 'sessions'; tab = 'overview'; await open(s) }

  function onKey(ev: KeyboardEvent) {
    if (view !== 'sessions' || !current || tab !== 'review') return
    const tag = (ev.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
    const list = events.filter((e) => e.event_type !== 'blink').sort((a, b) => a.start_us - b.start_us)
    if (ev.key === 'ArrowRight') { playhead = Math.min((current.duration_us ?? playhead + 1e6), playhead + (ev.shiftKey ? 5e6 : 1e6)); ev.preventDefault() }
    else if (ev.key === 'ArrowLeft') { playhead = Math.max(0, playhead - (ev.shiftKey ? 5e6 : 1e6)); ev.preventDefault() }
    else if (ev.key === 'j' || ev.key === 'k') {
      const i = selected ? list.findIndex((e) => e.event_id === selected!.event_id) : -1
      const next = ev.key === 'j' ? list[i + 1] : list[Math.max(0, i - 1)]
      if (next) pick(next)
    } else if (ev.key === 'Escape') { selected = null; if (compare && !compare.a) compare = null }
    else if (ev.key === 'c') compare = compare ? null : { a: null, b: null }
  }

  onMount(async () => {
    if (subjectMode) return
    window.addEventListener('keydown', onKey)
    await loadSettings()
    onboarding = !api.isDemo() && app.settings !== null && !app.settings.onboarded
    try { sessions = await api.sessions(); if (sessions[0]) await open(sessions[0]) } catch (e) { error = String(e) }
    return () => window.removeEventListener('keydown', onKey)
  })
</script>

{#if subjectMode}
<SubjectView />
{:else}
{#if onboarding}<Onboarding ondone={() => (onboarding = false)} />{/if}
{#if uploading}<UploadDialog onclose={() => (uploading = false)} ondone={async (id) => { uploading = false; view = 'sessions'; tab = 'overview'; await reload(id) }} />{/if}
<div class="app" class:with-rail={view === 'sessions'} class:with-panel={view === 'sessions' && tab === 'review'}>
  <header class="top">
    <div class="brand-nav">
      <button class="brand" onclick={() => (view = 'home')} aria-label="home">
        <span class="mark"></span><span class="name">Lightman</span>
      </button>
      <nav class="nav" aria-label="main">
        <button class:on={view === 'home'} onclick={() => (view = 'home')}>Home</button>
        <button class:on={view === 'clients'} onclick={() => (view = 'clients')}>Clients</button>
        <button class:on={view === 'sessions'} onclick={() => (view = 'sessions')}>Sessions</button>
        <button class:on={view === 'live'} onclick={() => (view = 'live')} disabled={api.isDemo()} title={api.isDemo() ? 'needs lightman serve' : ''}>Live</button>
        <button class:on={view === 'settings'} onclick={() => (view = 'settings')}>Settings</button>
      </nav>
    </div>
    <div class="top-right">
      {#if api.isDemo()}<span class="chip">demo data</span>{/if}
      <button class="upload" onclick={() => (uploading = true)} disabled={api.isDemo()}>Analyse a recording</button>
      <span class="profile" class:research={app.settings?.profile === 'research'} title="change in Settings">{app.settings?.profile ?? 'practice'}</span>
    </div>
  </header>

  {#if view === 'sessions'}<SessionRail {sessions} current={current?.session_id ?? null} onselect={open} />{/if}

  {#if view === 'home'}
    <HomeView {sessions} onlive={() => (view = 'live')} onupload={() => (uploading = true)} onopen={openSession} onclients={() => (view = 'clients')} />
  {:else if view === 'clients'}
    <ClientsView onopen={async (id) => { view = 'sessions'; tab = 'overview'; await reload(id) }} />
  {:else if view === 'settings'}
    <SettingsView />
  {:else if view === 'live'}
    <LiveView ondone={liveDone} />
  {:else}
  <main class="stage">
    {#if error}<div class="error">{error}</div>{/if}
    {#if current && detail}
      <div class="tabs" role="tablist">
        <div class="title"><span class="code mono">{current.subject_id ?? '-'}</span><span class="muted">{current.mode === 'live' ? 'live session' : current.media_name ?? ''}</span></div>
        <button role="tab" aria-selected={tab === 'overview'} class:on={tab === 'overview'} onclick={() => (tab = 'overview')}>Overview</button>
        <button role="tab" aria-selected={tab === 'review'} class:on={tab === 'review'} onclick={() => (tab = 'review')}>Review</button>
        <button role="tab" aria-selected={tab === 'conversation'} class:on={tab === 'conversation'} onclick={() => (tab = 'conversation')}>Conversation</button>
        {#if research()}<button role="tab" aria-selected={tab === 'research'} class:on={tab === 'research'} onclick={() => (tab = 'research')}>Research</button>{/if}
        <span class="spacer"></span>
        {#if tab === 'review'}<button class="cmpbtn" class:on={Boolean(compare)} onclick={() => (compare = compare ? null : { a: null, b: null })}>{compare ? 'exit compare' : 'compare spans'}</button>{/if}
        <a class="report" href={`./api/sessions/${current.session_id}/share`} target="_blank" rel="noopener">Report</a>
      </div>
      {#if tab === 'overview'}
        <div class="scroll">
          <PracticeCard sessionId={current.session_id} {playhead} onseek={(us) => { seekTo(us); tab = 'review' }} />
          <SummaryCard {detail} {events} />
          <KeyMoments {events} session={current} onpick={pick} />
          <NotesPanel sessionId={current.session_id} {playhead} onseek={(us) => { seekTo(us); tab = 'review' }} />
          <QualityStrip {detail} {events} />
        </div>
      {:else if tab === 'review'}
        <div class="review">
          <VideoStage session={current} {events} {selected} bind:playhead />
          <FramePanel sessionId={current.session_id} {playhead} />
          <Timeline {events} {video} {audio} {pulse} {protocol} baseline={detail.baseline} audioBaseline={detail.audio_baseline}
                    duration={current.duration_us ?? 0} bind:playhead {selected} onpick={pick} onseek={seekTo} {compare} onrange={setRange} />
          {#if compare}
            <ComparePanel sessionId={current.session_id} a={compare.a} b={compare.b} {protocol} onclear={() => (compare = null)} onpreset={(a, b) => (compare = { a, b })} />
          {/if}
          <p class="keys mono">arrows seek, shift+arrows 5 s, j/k next or previous event, c compare spans, esc clear</p>
        </div>
      {:else if tab === 'conversation'}
        <div class="scroll">
          <TranscriptPanel sessionId={current.session_id} {playhead} onseek={(us) => { seekTo(us); tab = 'review' }} />
          <ProtocolTable {protocol} onseek={(us) => { seekTo(us); tab = 'review' }} />
          <NotesPanel sessionId={current.session_id} {playhead} onseek={(us) => { seekTo(us); tab = 'review' }} />
        </div>
      {:else}
        <div class="scroll">
          <SummaryCard {detail} {events} researchOnly />
          <ProtocolTable {protocol} onseek={(us) => { seekTo(us); tab = 'review' }} />
          <HistoryCard sessionId={current.session_id} />
        </div>
      {/if}
    {:else if !loading}
      <div class="empty">
        <p class="eyebrow">no sessions yet</p>
        <p>Start a live session, or analyse a recording with the button at the top.</p>
      </div>
    {/if}
  </main>
  {/if}

  {#if view === 'sessions' && tab === 'review'}<EventPanel {selected} {events} session={current} baseline={detail?.baseline ?? null} onpick={pick} />{/if}
</div>
{/if}

<style>
  .app {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: 48px minmax(0, 1fr);
    grid-template-areas: "top" "stage";
    height: 100vh;
  }
  .app.with-rail { grid-template-columns: 232px minmax(0, 1fr); grid-template-areas: "top top" "rail stage"; }
  .app.with-rail.with-panel { grid-template-columns: 232px minmax(0, 1fr) 340px; grid-template-areas: "top top top" "rail stage panel"; }
  .top { grid-area: top; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; border-bottom: 1px solid var(--line); background: var(--panel); gap: 12px; }
  .brand-nav { display: flex; align-items: center; gap: 20px; min-width: 0; }
  .brand { display: flex; align-items: center; gap: 10px; background: none; border: 0; padding: 0; color: var(--text); cursor: pointer; }
  .mark { width: 11px; height: 11px; border: 2px solid var(--accent); transform: rotate(45deg); display: inline-block; }
  .name { font-weight: 600; letter-spacing: 0.02em; font-size: 15px; }
  .nav { display: flex; gap: 2px; overflow-x: auto; }
  .nav button { background: none; border-color: transparent; color: var(--muted); padding: 5px 11px; font-size: 13px; }
  .nav button.on { color: var(--text); border-color: var(--line-strong); background: var(--panel-2); }
  .nav button:disabled { opacity: 0.4; cursor: default; }
  .top-right { display: flex; gap: 10px; align-items: center; font-size: 12px; }
  .upload { padding: 5px 12px; font-size: 12.5px; border-color: var(--accent); color: var(--accent); }
  .profile { font: 500 10.5px/1 var(--font-data); text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); border: 1px solid var(--line-strong); padding: 4px 7px; border-radius: 3px; }
  .profile.research { color: var(--violet); border-color: var(--violet); }
  .chip { border: 1px solid var(--accent); color: var(--accent); padding: 1px 7px; border-radius: 10px; font-size: 11px; }
  .stage { grid-area: stage; display: flex; flex-direction: column; min-height: 0; background: var(--ground); }
  .tabs { display: flex; align-items: center; gap: 4px; padding: 8px 16px; border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap; }
  .tabs .title { display: flex; gap: 10px; align-items: baseline; margin-right: 14px; font-size: 13px; }
  .tabs .code { color: var(--accent); font-size: 14px; }
  .tabs button[role='tab'] { background: none; border-color: transparent; color: var(--muted); padding: 4px 11px; font-size: 13px; }
  .tabs button[role='tab'].on { color: var(--text); border-color: var(--line-strong); background: var(--panel-2); }
  .spacer { flex: 1; }
  .report { border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 3px 10px; color: var(--text); text-decoration: none; font-size: 12px; }
  .scroll { overflow-y: auto; min-height: 0; flex: 1; }
  .review { display: grid; grid-template-rows: minmax(260px, 1fr) auto auto auto auto; min-height: 0; flex: 1; overflow-y: auto; }
  .keys { font-size: 10.5px; color: var(--faint); margin: 6px 16px 10px; }
  .empty { padding: 48px; color: var(--muted); }
  .error { margin: 12px; padding: 10px 12px; border: 1px solid var(--warn); color: var(--warn); border-radius: var(--radius); }
  code { background: var(--panel-2); padding: 1px 5px; border-radius: 3px; }
  .cmpbtn { padding: 2px 9px; font-size: 11px; }
  .cmpbtn.on { border-color: var(--accent); color: var(--accent); }
  .muted { color: var(--muted); }
</style>
