export interface SessionSummary {
  session_id: string
  created_utc: string | null
  mode: string
  media_name: string | null
  duration_us: number | null
  face_coverage: number | null
  baseline_quality: number | null
  events: number
  has_audio: boolean
  has_media: boolean
}

export interface Contribution {
  feature: string
  unit: string
  peak_value: number
  baseline_center: number
  baseline_scale: number
  peak_deviation: number
  direction: 'increase' | 'decrease'
}

export interface LmEvent {
  event_id: string
  subject_id: string
  source: string
  event_type: string
  level: 'observation' | 'interpretation' | 'inference'
  start_us: number
  end_us: number
  peak_us: number | null
  label: string
  description: string
  contributions: Contribution[]
  severity: number
  confidence: number
  quality: number
  baseline_quality: number
  extractor_id: string
  tags: string[]
}

export interface SignalBaseline {
  feature: string
  unit: string
  center: number | null
  scale: number | null
  n: number
  floor_applied: boolean
}

export interface Baseline {
  mode: string
  window_start_us: number
  window_end_us: number
  frames_in_window: number
  frames_used: number
  quality: number
  notes: string[]
  signals: Record<string, SignalBaseline>
}

export interface SessionDetail {
  manifest: any
  analysis: any
  baseline: Baseline | null
  audio_baseline: Baseline | null
  segments: { segments: any[] } | null
}

export interface FeatureSeries {
  t_us: number[]
  columns: string[]
  signals: Record<string, (number | null)[]>
  decimated: boolean
  rows: number
}
