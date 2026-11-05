// Shared application settings (profile, practitioner, onboarding) and system status.
import { api } from './api'
import type { Settings } from './types'

export const app = $state<{ settings: Settings | null; system: any | null }>({ settings: null, system: null })

export async function loadSettings(): Promise<void> {
  try { app.settings = await api.settings() } catch { app.settings = { profile: 'practice', require_consent: true, onboarded: true, practitioner: '' } }
  try { app.system = await api.system() } catch { app.system = null }
}

export async function saveSettings(s: Partial<Settings>): Promise<void> {
  app.settings = await api.saveSettings(s)
}

export function research(): boolean { return app.settings?.profile === 'research' }
