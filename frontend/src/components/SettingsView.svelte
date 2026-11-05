<script lang="ts">
  import { app, saveSettings } from '../lib/settings.svelte'
  let initials = $state(app.settings?.practitioner ?? '')
  let saved = $state('')
  async function setProfile(p: 'practice' | 'research') { await saveSettings({ profile: p }); saved = 'Saved.' }
  async function saveInitials() { await saveSettings({ practitioner: initials.trim() }); saved = 'Saved.' }
  const mb = (b: number | null) => (b == null ? '' : `${(b / 1e6).toFixed(b > 1e7 ? 0 : 1)} MB`)
</script>

<section class="settings">
  <header><span class="eyebrow">settings</span><h1>Settings</h1></header>
  <div class="group">
    <h2>Profile</h2>
    <div class="opts">
      <button class="opt" class:on={app.settings?.profile !== 'research'} onclick={() => setProfile('practice')}><b>Practice</b><span>Affect, engagement, talk time, notes and client trends. Deception-research cues are hidden.</span></button>
      <button class="opt" class:on={app.settings?.profile === 'research'} onclick={() => setProfile('research')}><b>Research</b><span>Everything in practice plus deception-research cues, the possibility index, validation games and raw signal views.</span></button>
    </div>
  </div>
  <div class="group">
    <h2>You</h2>
    <label class="field" for="set-initials">Initials saved with consent records<span class="row"><input id="set-initials" bind:value={initials} maxlength="64" /><button onclick={saveInitials}>Save</button></span></label>
    {#if saved}<span class="muted ok">{saved}</span>{/if}
  </div>
  <div class="group">
    <h2>Consent</h2>
    <p>{app.settings?.require_consent ? 'A consent record is required before every live session and every analysed recording.' : 'Consent records are optional on this installation (practice.require_consent = false).'}</p>
  </div>
  {#if app.system}
    <div class="group">
      <h2>This machine</h2>
      <dl>
        <dt>Version</dt><dd class="mono">{app.system.version}</dd>
        <dt>Data folder</dt><dd class="mono">{app.system.data_dir}</dd>
        <dt>Network access</dt><dd>{app.system.network ? 'on: other devices can connect with the access link' : 'off: this machine only'}</dd>
        <dt>Speech-to-text</dt><dd>{app.system.speech_installed ? 'installed' : 'not installed (pip install "lightman[asr]")'}</dd>
        <dt>Benchmark</dt><dd>{app.system.bench ? `live facial model: ${app.system.bench.live_au_model.split('/')[1]} (measured ${app.system.bench.created?.slice(0, 10)})` : 'not run yet: lightman bench'}</dd>
      </dl>
      <table>
        <thead><tr><th>model</th><th>status</th><th>size</th></tr></thead>
        <tbody>
          {#each app.system.models as m (m.id)}<tr><td class="mono">{m.id}</td><td class:missing={!m.cached}>{m.cached ? 'ready' : 'downloads on first use'}</td><td class="mono">{mb(m.bytes)}</td></tr>{/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  .settings { grid-area: stage; overflow-y: auto; padding: 28px 36px; display: flex; flex-direction: column; gap: 22px; background: var(--ground); max-width: 900px; }
  h1 { margin: 4px 0 0; font-size: 24px; font-weight: 600; }
  h2 { margin: 0 0 8px; font-size: 14px; font-weight: 600; }
  .group { display: flex; flex-direction: column; gap: 6px; }
  .opts { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
  .opt { display: flex; flex-direction: column; gap: 4px; text-align: left; padding: 14px; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; color: var(--text); cursor: pointer; }
  .opt span { font-size: 12.5px; color: var(--muted); line-height: 1.45; }
  .opt.on { border-color: var(--accent); }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
  .row { display: flex; gap: 8px; }
  input { background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: var(--radius); color: var(--text); padding: 6px 8px; font: 13px var(--font-ui); }
  .ok { font-size: 12px; color: var(--ok); }
  p { margin: 0; font-size: 13px; color: var(--muted); }
  dl { display: grid; grid-template-columns: 140px minmax(0, 1fr); gap: 6px 14px; margin: 0 0 10px; font-size: 13px; }
  dt { color: var(--muted); }
  dd { margin: 0; overflow-wrap: anywhere; }
  table { border-collapse: collapse; width: 100%; font-size: 12.5px; background: var(--panel); border: 1px solid var(--line); }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 400; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
  .missing { color: var(--accent); }
</style>
