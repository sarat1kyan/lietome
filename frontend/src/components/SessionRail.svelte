<script lang="ts">
  import type { SessionSummary } from '../lib/types'
  import { tc } from '../lib/api'
  let { sessions, current, onselect }: { sessions: SessionSummary[]; current: string | null; onselect: (s: SessionSummary) => void } = $props()
  const when = (s: string | null) => (s ? s.replace('T', ' ').replace('+00:00', 'Z') : '')
  let q = $state('')
  const shown = $derived.by(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return sessions
    return sessions.filter((s) => [s.session_id, s.media_name ?? '', s.subject_id ?? '', s.mode, when(s.created_utc)].join(' ').toLowerCase().includes(needle))
  })
  const subjects = $derived(new Set(sessions.map((s) => s.subject_id).filter(Boolean)).size)
</script>

<aside class="rail">
  <div class="head"><span class="eyebrow">sessions</span><span class="mono muted">{shown.length}{subjects > 1 ? ` / ${subjects} subjects` : ''}</span></div>
  <input class="search" type="search" placeholder="filter by name, subject, date" bind:value={q} aria-label="filter sessions" />
  <ul>
    {#each shown as s (s.session_id)}
      <li>
        <button class="item" class:active={s.session_id === current} onclick={() => onselect(s)}>
          <div class="row1"><span class="media">{s.media_name ?? s.session_id}</span><span class="mode mono">{s.mode}{s.subject_id && s.subject_id !== 'subject_001' ? ` ${s.subject_id}` : ''}</span></div>
          <div class="row2 mono muted">
            <span>{s.duration_us ? tc(s.duration_us) : '--:--:--.---'}</span>
            <span>{s.events} ev</span>
            <span title="face coverage">face {s.face_coverage != null ? Math.round(s.face_coverage * 100) + '%' : '-'}</span>
          </div>
          <div class="row3 muted">{when(s.created_utc)}</div>
        </button>
      </li>
    {/each}
  </ul>
</aside>

<style>
  .rail { grid-area: rail; border-right: 1px solid var(--line); background: var(--panel); overflow-y: auto; min-height: 0; }
  .head { display: flex; justify-content: space-between; padding: 12px 14px 8px; }
  .search { display: block; width: calc(100% - 28px); margin: 0 14px 8px; background: var(--panel-2); border: 1px solid var(--line); border-radius: var(--radius); color: var(--text); padding: 4px 8px; font-size: 11.5px; }
  .search:focus { outline: none; border-color: var(--line-strong); }
  ul { list-style: none; margin: 0; padding: 0; }
  .item { display: block; width: 100%; text-align: left; background: none; border: 0; border-left: 2px solid transparent; border-bottom: 1px solid var(--line); border-radius: 0; padding: 10px 14px; }
  .item:hover { background: var(--panel-2); }
  .item.active { border-left-color: var(--accent); background: var(--panel-2); }
  .row1 { display: flex; justify-content: space-between; gap: 8px; }
  .media { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mode { font-size: 10.5px; color: var(--muted); }
  .row2 { display: flex; gap: 10px; font-size: 11px; margin-top: 3px; }
  .row3 { font-size: 10.5px; margin-top: 2px; }
</style>
