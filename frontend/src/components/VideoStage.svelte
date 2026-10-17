<script lang="ts">
  import { api, tc } from '../lib/api'
  import { drawHud } from '../lib/hud'
  import type { FrameSnapshot } from '../lib/types'
  import type { LmEvent, SessionSummary } from '../lib/types'
  let { session, events, selected, playhead = $bindable(0) }: { session: SessionSummary; events: LmEvent[]; selected: LmEvent | null; playhead: number } = $props()

  let videoEl = $state<HTMLVideoElement | null>(null)
  let localUrl = $state<string | null>(null)
  let src = $derived(localUrl ?? api.mediaUrl(session.session_id, session.has_media))
  let thumb = $derived(selected ? api.thumbnail(session.session_id, selected.event_id) : null)
  let syncing = false
  let offsetUs = $state(0)
  let overlay = $state<HTMLCanvasElement | null>(null)
  let showHud = $state(true)
  let snap: FrameSnapshot | null = null
  let snapTimer: ReturnType<typeof setTimeout> | null = null
  $effect(() => { const id = session.session_id; offsetUs = 0; if (session.has_media) api.mediaInfo(id).then((m) => { if (m && id === session.session_id) offsetUs = m.offset_us ?? 0 }) })
  // measurements at the playhead for the replayed HUD (debounced; newest wins)
  $effect(() => {
    const t = playhead, id = session.session_id
    if (!src || !showHud) return
    if (snapTimer) clearTimeout(snapTimer)
    snapTimer = setTimeout(async () => { try { snap = await api.frame(id, t); paint() } catch { /* keep last */ } }, 60)
  })
  function paint() {
    const c = overlay, v = videoEl
    if (!c || !v || !v.videoWidth) return
    const dpr = window.devicePixelRatio || 1
    const rect = v.getBoundingClientRect()
    c.width = rect.width * dpr; c.height = rect.height * dpr
    c.style.width = rect.width + 'px'; c.style.height = rect.height + 'px'
    c.style.left = v.offsetLeft + 'px'; c.style.top = v.offsetTop + 'px'
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height)
    if (!showHud || !snap || snap.t_us == null) return
    const val: Record<string, number> = {}
    for (const [k, x] of Object.entries(snap.values)) if (x != null) val[k] = x
    const b = ['face.bbox_x0', 'face.bbox_y0', 'face.bbox_x1', 'face.bbox_y1'].map((k) => val[k])
    const base: Record<string, { center: number; scale: number }> = {}
    for (const [k, x] of Object.entries(snap.baseline)) if (x.center != null && x.scale) base[k] = { center: x.center, scale: x.scale }
    drawHud({
      ctx, w: rect.width, h: rect.height, map: { ox: 0, oy: 0, dw: rect.width, dh: rect.height },
      landmarks: null, bbox: b.every((x) => x != null) ? (b as [number, number, number, number]) : null,
      values: val, base, baselineReady: true, tUs: snap.t_us, stats: { analyzed_fps: 0, latency_ms_p50: null, frames_dropped: 0 },
      audio: null, pulse: null, pulseWave: null, gazeAwaySinceUs: null, blinkAgoMs: 1e9, flashes: [], now: performance.now(),
      tape: [], windowUs: 30e6, question: null, phase: null, ticker: null, lastIndex: null, hints: [], serverPatterns: null,
      body: null, full: true, mode: 'replay',
    })
  }

  // Seek the video when the playhead moves from the timeline or an event pick.
  $effect(() => {
    const el = videoEl
    if (!el || !src || syncing) return
    const t = Math.max(0, (playhead - offsetUs) / 1e6)
    if (Math.abs(el.currentTime - t) > 0.04) el.currentTime = t
  })

  function onTime() {
    if (!videoEl) return
    syncing = true
    playhead = Math.round(videoEl.currentTime * 1e6) + offsetUs
    queueMicrotask(() => (syncing = false))
  }
  function chooseFile(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0]
    if (!f) return
    if (localUrl) URL.revokeObjectURL(localUrl)
    localUrl = URL.createObjectURL(f) // stays in this browser; nothing is uploaded
  }
  const activeNow = $derived(events.filter((e) => e.start_us <= playhead && playhead <= e.end_us && e.event_type !== 'blink'))
</script>

<section class="video">
  <div class="frame">
    {#if src}
      <video bind:this={videoEl} {src} controls preload="metadata" ontimeupdate={onTime} onseeked={onTime} onloadedmetadata={paint}></video>
      <canvas bind:this={overlay} class="hud"></canvas>
    {:else if thumb}
      <img class="still" src={thumb} alt="" />
      <div class="hint">event still. attach the original file to scrub the video: it stays on this machine.</div>
    {:else}
      <div class="hint">no media retained for this session. attach the original file to play it locally.</div>
    {/if}
    <div class="overlay top">
      <span class="mono">{tc(playhead)}</span>
      <span class="eyebrow">{session.media_name ?? session.session_id}</span>
    </div>
    {#if activeNow.length}
      <div class="overlay bottom">
        {#each activeNow.slice(0, 4) as e (e.event_id)}
          <span class="tag" class:audio={e.source === 'audio'}>{e.label}</span>
        {/each}
      </div>
    {/if}
  </div>
  <div class="bar">
    <label class="attach">
      <input type="file" accept="video/*,audio/*" onchange={chooseFile} />
      <span>attach original media</span>
    </label>
    <span class="muted">local playback only</span>
    {#if src}<label class="hudtoggle"><input type="checkbox" bind:checked={showHud} onchange={paint} /> overlays</label>{/if}
  </div>
</section>

<style>
  .video { display: grid; grid-template-rows: minmax(0, 1fr) auto; min-height: 0; padding: 12px 16px 0; }
  .frame { position: relative; background: #05070a; border: 1px solid var(--line); border-radius: var(--radius); min-height: 0; display: grid; place-items: center; overflow: hidden; }
  video, .still { max-width: 100%; max-height: 100%; width: auto; height: auto; display: block; }
  .hint { color: var(--muted); padding: 24px; text-align: center; max-width: 42ch; }
  .overlay { position: absolute; left: 0; right: 0; display: flex; gap: 12px; padding: 8px 12px; pointer-events: none; }
  .overlay.top { top: 0; justify-content: space-between; background: linear-gradient(rgba(5,7,10,0.75), transparent); }
  .overlay.bottom { bottom: 0; flex-wrap: wrap; background: linear-gradient(transparent, rgba(5,7,10,0.8)); }
  .tag { border: 1px solid var(--accent); color: var(--accent); background: rgba(5,7,10,0.6); padding: 2px 8px; font-size: 11.5px; border-radius: 2px; }
  .tag.audio { border-color: var(--teal); color: var(--teal); }
  .bar { display: flex; align-items: center; gap: 12px; padding: 8px 2px; font-size: 12px; }
  .attach input { display: none; }
  .hud { position: absolute; pointer-events: none; }
  .hudtoggle { margin-left: auto; }
  .attach span { border: 1px solid var(--line-strong); padding: 4px 10px; border-radius: var(--radius); cursor: pointer; }
  .attach span:hover { border-color: var(--muted); }
</style>
