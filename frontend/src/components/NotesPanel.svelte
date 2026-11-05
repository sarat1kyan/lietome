<script lang="ts">
  import { api, tc } from '../lib/api'
  import type { Note } from '../lib/types'
  let { sessionId, playhead, onseek, onchange = () => {} }: { sessionId: string; playhead: number; onseek: (us: number) => void; onchange?: (n: Note[]) => void } = $props()
  let notes = $state<Note[]>([])
  let text = $state('')
  let pin = $state(true)
  let editing = $state<string | null>(null)
  let editText = $state('')
  $effect(() => { const id = sessionId; notes = []; api.notes(id).then((n) => { if (id === sessionId) { notes = n; onchange(n) } }).catch(() => {}) })
  async function add() {
    const t = text.trim(); if (!t) return
    await api.addNote(sessionId, t, pin ? Math.round(playhead) : null)
    text = ''; notes = await api.notes(sessionId); onchange(notes)
  }
  async function save(n: Note) {
    const t = editText.trim(); if (!t) return
    await api.editNote(sessionId, n.id, t, n.t_us); editing = null; notes = await api.notes(sessionId); onchange(notes)
  }
  async function remove(n: Note) { await api.deleteNote(sessionId, n.id); notes = await api.notes(sessionId); onchange(notes) }
</script>

<section class="notes" aria-label="session notes">
  <div class="hdr"><span class="eyebrow">notes</span><span class="muted">your observations, kept with the session. pinned notes appear on the timeline.</span></div>
  <div class="add">
    <textarea id="note-text" rows="2" placeholder="Write a note..." bind:value={text} onkeydown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) add() }}></textarea>
    <div class="add-row">
      <label><input type="checkbox" bind:checked={pin} /> pin at {tc(playhead).slice(3)}</label>
      <button class="primary" onclick={add} disabled={!text.trim()}>Add note</button>
    </div>
  </div>
  <ul>
    {#each notes as n (n.id)}
      <li>
        {#if n.t_us != null}<button class="t mono" onclick={() => onseek(n.t_us!)}>{tc(n.t_us).slice(3)}</button>{:else}<span class="t mono muted">general</span>{/if}
        {#if editing === n.id}
          <textarea rows="2" bind:value={editText}></textarea>
          <span class="acts"><button onclick={() => save(n)}>save</button><button onclick={() => (editing = null)}>cancel</button></span>
        {:else}
          <p>{n.text}</p>
          <span class="acts"><button onclick={() => { editing = n.id; editText = n.text }}>edit</button><button onclick={() => remove(n)}>delete</button></span>
        {/if}
      </li>
    {:else}<li class="empty muted">No notes yet.</li>{/each}
  </ul>
</section>

<style>
  .notes { border-top: 1px solid var(--line); background: var(--panel); padding: 10px 16px 12px; }
  .hdr { display: flex; gap: 12px; align-items: baseline; font-size: 11.5px; }
  .add { display: flex; flex-direction: column; gap: 6px; margin: 8px 0; }
  textarea { width: 100%; box-sizing: border-box; background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: var(--radius); color: var(--text); padding: 6px 8px; font: 13px/1.45 var(--font-ui); resize: vertical; }
  .add-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--muted); }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  li { display: grid; grid-template-columns: 64px minmax(0, 1fr) auto; gap: 10px; align-items: start; font-size: 13px; }
  li p { margin: 0; line-height: 1.45; white-space: pre-wrap; }
  .t { background: none; border: 0; color: var(--accent); padding: 0; cursor: pointer; font-size: 12px; text-align: left; }
  .acts { display: flex; gap: 4px; }
  .acts button { padding: 1px 7px; font-size: 11px; }
  .empty { grid-template-columns: 1fr; font-size: 12px; }
</style>
