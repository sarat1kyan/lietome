<script lang="ts">
  import { api, tc } from '../lib/api'
  import type { LmEvent, SessionSummary } from '../lib/types'
  let { session, events, selected, playhead = $bindable(0) }: { session: SessionSummary; events: LmEvent[]; selected: LmEvent | null; playhead: number } = $props()

  let videoEl = $state<HTMLVideoElement | null>(null)
  let localUrl = $state<string | null>(null)
  let src = $derived(localUrl ?? api.mediaUrl(session.session_id, session.has_media))
  let thumb = $derived(selected ? api.thumbnail(session.session_id, selected.event_id) : null)
  let syncing = false

  // Seek the video when the playhead moves from the timeline or an event pick.
  $effect(() => {
    const el = videoEl
    if (!el || !src || syncing) return
    const t = playhead / 1e6
    if (Math.abs(el.currentTime - t) > 0.04) el.currentTime = t
  })

  function onTime() {
    if (!videoEl) return
    syncing = true
    playhead = Math.round(videoEl.currentTime * 1e6)
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
      <video bind:this={videoEl} {src} controls preload="metadata" ontimeupdate={onTime} onseeked={onTime}></video>
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
  .attach span { border: 1px solid var(--line-strong); padding: 4px 10px; border-radius: var(--radius); cursor: pointer; }
  .attach span:hover { border-color: var(--muted); }
</style>
