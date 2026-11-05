<script lang="ts">
  import { api } from '../lib/api'
  import type { ClientRow, Consent, ConsentScope } from '../lib/types'

  let { onconfirm, oncancel, wantAudio = true, wantRecording = false }: {
    onconfirm: (client: string, consent: Consent) => void
    oncancel: () => void
    wantAudio?: boolean
    wantRecording?: boolean
  } = $props()

  let clients = $state<ClientRow[]>([])
  let code = $state('')
  let newCode = $state('')
  let givenBy = $state<Consent['given_by']>('client')
  let method = $state<Consent['method']>('verbal')
  let scope = $state<Record<ConsentScope, boolean>>({ video_analysis: true, audio_analysis: wantAudio, recording: wantRecording, transcription: wantAudio })
  let initials = $state('')
  let note = $state('')
  let agreed = $state(false)
  let err = $state('')
  api.clients().then((c) => { clients = c; if (c.length && !code) code = c[0].code }).catch(() => {})
  api.settings().then((s) => (initials = s.practitioner)).catch(() => {})

  const chosen = $derived(code === '__new' ? newCode.trim() : code)
  const valid = $derived(/^[A-Za-z0-9_-]{1,32}$/.test(chosen) && scope.video_analysis && agreed)

  async function confirm() {
    err = ''
    if (!valid) return
    if (code === '__new') {
      try { await api.saveClient(chosen, {}) } catch (e) { err = String(e); return }
    }
    onconfirm(chosen, {
      given_by: givenBy, method, confirmed_by: initials.trim(), note: note.trim(),
      scope: (Object.keys(scope) as ConsentScope[]).filter((k) => scope[k]),
    })
  }
</script>

<div class="backdrop" role="presentation">
  <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="consent-title">
    <h2 id="consent-title">Before you start</h2>
    <p class="lead">Confirm who is being analysed and what they agreed to. The record is saved with the session and limits what Lightman does.</p>

    <label class="field" for="consent-client">Client
      <select id="consent-client" bind:value={code}>
        {#each clients as c (c.code)}<option value={c.code}>{c.code}{c.label ? ` (${c.label})` : ''}</option>{/each}
        <option value="__new">new client...</option>
      </select>
    </label>
    {#if code === '__new' || !clients.length}
      <label class="field" for="consent-code">Client code <span class="hint">use a code, not a name (for example C-014)</span>
        <input id="consent-code" bind:value={newCode} maxlength="32" placeholder="C-001" onfocus={() => (code = '__new')} />
      </label>
    {/if}

    <div class="row">
      <label class="field" for="consent-by">Agreed by
        <select id="consent-by" bind:value={givenBy}><option value="client">the client</option><option value="guardian">a legal guardian</option><option value="self">myself (self-analysis)</option></select>
      </label>
      <label class="field" for="consent-method">How
        <select id="consent-method" bind:value={method}><option value="verbal">verbally</option><option value="written">in writing</option><option value="electronic">electronically</option></select>
      </label>
    </div>

    <fieldset>
      <legend>They agreed to</legend>
      <label><input type="checkbox" bind:checked={scope.video_analysis} disabled /> analysis of face, head, eyes and posture (required)</label>
      <label><input type="checkbox" bind:checked={scope.audio_analysis} /> analysis of voice (pitch, loudness, pauses)</label>
      <label><input type="checkbox" bind:checked={scope.transcription} disabled={!scope.audio_analysis} /> a transcript of what is said (made on this machine)</label>
      <label><input type="checkbox" bind:checked={scope.recording} /> keeping a video recording of the session on this machine</label>
    </fieldset>

    <div class="row">
      <label class="field" for="consent-initials">Your initials<input id="consent-initials" bind:value={initials} maxlength="64" /></label>
      <label class="field grow" for="consent-note">Note (optional)<input id="consent-note" bind:value={note} maxlength="500" /></label>
    </div>

    <label class="agree"><input type="checkbox" bind:checked={agreed} /> I explained what is measured, that it is not a diagnosis or a lie detector, and that they can stop at any time.</label>
    {#if err}<p class="err">{err}</p>{/if}
    <div class="actions">
      <button onclick={oncancel}>Cancel</button>
      <button class="primary" disabled={!valid} onclick={confirm}>Start session</button>
    </div>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(5, 7, 10, 0.72); display: grid; place-items: center; z-index: 50; padding: 16px; }
  .dialog { width: min(560px, 100%); max-height: calc(100vh - 32px); overflow-y: auto; background: var(--panel); border: 1px solid var(--line-strong); border-radius: 6px; padding: 22px 24px; display: flex; flex-direction: column; gap: 12px; }
  h2 { margin: 0; font-size: 18px; font-weight: 600; }
  .lead { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.5; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
  .field.grow { flex: 1; }
  .hint { color: var(--faint); }
  input, select { background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: var(--radius); color: var(--text); padding: 6px 8px; font: 13px var(--font-ui); }
  input:focus, select:focus { outline: 1px solid var(--accent); }
  .row { display: flex; gap: 12px; flex-wrap: wrap; }
  .row .field { min-width: 150px; }
  fieldset { border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
  legend { color: var(--muted); font-size: 12px; padding: 0 4px; }
  .agree { font-size: 13px; line-height: 1.45; display: flex; gap: 8px; align-items: flex-start; }
  .err { color: var(--warn); font-size: 12px; margin: 0; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; }
  button { padding: 6px 14px; }
</style>
