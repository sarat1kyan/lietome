<script lang="ts">
  import { app, saveSettings } from '../lib/settings.svelte'
  let { ondone }: { ondone: () => void } = $props()
  let step = $state(0)
  let initials = $state(app.settings?.practitioner ?? '')
  let profile = $state<'practice' | 'research'>(app.settings?.profile ?? 'practice')
  async function finish() { await saveSettings({ onboarded: true, practitioner: initials.trim(), profile }); ondone() }
</script>

<div class="backdrop" role="presentation">
  <div class="card" role="dialog" aria-modal="true" aria-labelledby="ob-title">
    <div class="steps mono">{step + 1} / 3</div>
    {#if step === 0}
      <h1 id="ob-title">Lightman measures how a person's face, voice and posture move, against their own baseline.</h1>
      <ul>
        <li><b>Expressed affect</b>: how positive or negative, calm or activated the face and voice look, compared with the start of the session.</li>
        <li><b>Engagement and talk time</b>: how much the person was turned to the conversation and how much of the speaking was theirs.</li>
        <li><b>Moments to revisit</b>: expressions, gestures, pauses and changes, with the video, transcript and your notes side by side.</li>
      </ul>
      <p class="muted">Everything runs on this machine. Nothing is uploaded anywhere.</p>
    {:else if step === 1}
      <h1 id="ob-title">What it is not</h1>
      <ul>
        <li>It does not read minds, diagnose, or tell what someone feels. A smile is a smile, not happiness.</li>
        <li>It is not a lie detector. Research cues for deception are weak; they stay in the research profile.</li>
        <li>It needs consent. Before every session you record who agreed and to what: analysis, voice, transcript, recording.</li>
      </ul>
      <p class="muted">Use the numbers to notice change within one person over time, and to decide what to ask next.</p>
    {:else}
      <h1 id="ob-title">Set up</h1>
      <label class="field" for="ob-initials">Your initials (saved with consent records)<input id="ob-initials" bind:value={initials} maxlength="64" placeholder="e.g. M.S." /></label>
      <fieldset>
        <legend>Profile</legend>
        <label><input type="radio" bind:group={profile} value="practice" /> <b>Practice</b>: affect, engagement, talk time, notes, client trends.</label>
        <label><input type="radio" bind:group={profile} value="research" /> <b>Research</b>: everything in practice, plus deception-research cues, validation games and raw signal views.</label>
      </fieldset>
      <p class="muted">You can change this later in Settings.</p>
    {/if}
    <div class="actions">
      {#if step > 0}<button onclick={() => step--}>Back</button>{/if}
      {#if step < 2}<button class="primary" onclick={() => step++}>Next</button>{:else}<button class="primary" onclick={finish}>Start using Lightman</button>{/if}
    </div>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(5, 7, 10, 0.8); display: grid; place-items: center; z-index: 60; padding: 16px; }
  .card { width: min(620px, 100%); background: var(--panel); border: 1px solid var(--line-strong); border-radius: 8px; padding: 28px 30px 22px; display: flex; flex-direction: column; gap: 14px; }
  .steps { color: var(--faint); font-size: 11px; }
  h1 { margin: 0; font-size: 21px; line-height: 1.3; font-weight: 600; text-wrap: balance; }
  ul { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 8px; font-size: 14px; line-height: 1.5; }
  b { font-weight: 600; }
  .muted { margin: 0; font-size: 13px; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
  input[type='text'], input:not([type]) { background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: var(--radius); color: var(--text); padding: 7px 9px; font: 14px var(--font-ui); }
  fieldset { border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; font-size: 13.5px; line-height: 1.45; }
  legend { color: var(--muted); font-size: 12px; padding: 0 4px; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
  button { padding: 7px 16px; }
</style>
