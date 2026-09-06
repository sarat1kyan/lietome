// Browser-side live capture: getUserMedia -> JPEG frames over WebSocket -> server analyzer.
// Protocol (binary, client -> server): 1 byte kind (1 = video jpeg, 2 = audio pcm f32 16 kHz),
// 8 bytes big-endian t_us, payload. Text (both ways): JSON messages.

export interface LiveFrameMsg {
  type: 'frame'
  t_us: number
  face: boolean
  quality: number
  bbox: [number, number, number, number] | null
  values: Record<string, number>
  landmarks: number[] | null // flat x,y normalized, 478 points
  baseline_ready: boolean
  stats: { analyzed_fps: number; latency_ms_p50: number | null; frames_dropped: number; frames_analyzed: number }
}
export interface LiveEventsMsg { type: 'events'; events: any[] }
export interface LiveAudioMsg { type: 'audio'; t_us: number; speech_prob: number; f0_hz: number | null; energy_db: number; baseline_ready: boolean }
export interface LiveSessionMsg { type: 'session'; session_id: string }
export interface LiveErrorMsg { type: 'error'; detail: string }
export type LiveMsg = LiveFrameMsg | LiveEventsMsg | LiveAudioMsg | LiveSessionMsg | LiveErrorMsg | { type: 'ready'; session_id: string }

export interface LiveOptions {
  au: boolean
  audio: boolean
  fps: number
  width: number
  jpegQuality: number
  onmessage: (m: LiveMsg) => void
  onstate: (s: 'connecting' | 'running' | 'stopped' | 'error', detail?: string) => void
}

function header(kind: number, tUs: number, payload: ArrayBuffer): ArrayBuffer {
  const out = new Uint8Array(9 + payload.byteLength)
  out[0] = kind
  const dv = new DataView(out.buffer)
  dv.setBigUint64(1, BigInt(Math.max(0, Math.round(tUs))))
  out.set(new Uint8Array(payload), 9)
  return out.buffer
}

export class LiveSession {
  private ws: WebSocket | null = null
  private stream: MediaStream | null = null
  private timer: number | null = null
  private inflight = 0
  private t0: number | null = null
  private audioCtx: AudioContext | null = null
  private audioNode: ScriptProcessorNode | null = null
  video: HTMLVideoElement

  constructor(video: HTMLVideoElement, private opts: LiveOptions) {
    this.video = video
  }

  async start(deviceId?: string) {
    this.opts.onstate('connecting')
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { deviceId: deviceId ? { exact: deviceId } : undefined, width: { ideal: this.opts.width }, frameRate: { ideal: 30 } },
      audio: this.opts.audio ? { channelCount: 1, echoCancellation: true, noiseSuppression: false } : false,
    })
    this.video.srcObject = this.stream
    await this.video.play()
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const base = new URL('.', location.href).pathname.replace(/\/$/, '')
    this.ws = new WebSocket(`${proto}://${location.host}${base}/api/live`)
    this.ws.binaryType = 'arraybuffer'
    this.ws.onopen = () => {
      this.ws!.send(JSON.stringify({ type: 'start', au: this.opts.au, audio: this.opts.audio, source: 'browser camera' }))
    }
    this.ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data) as LiveMsg
      if (m.type === 'ready') { this.t0 = performance.now(); this.opts.onstate('running'); this.loop(); if (this.opts.audio) this.startAudio() }
      if (m.type === 'frame') this.inflight = Math.max(0, this.inflight - 1)
      if (m.type === 'error') this.opts.onstate('error', m.detail)
      this.opts.onmessage(m)
    }
    this.ws.onclose = () => { this.cleanup(); this.opts.onstate('stopped') }
    this.ws.onerror = () => this.opts.onstate('error', 'websocket error')
  }

  private loop() {
    const canvas = document.createElement('canvas')
    const period = 1000 / this.opts.fps
    const tick = async () => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
      // at most 2 frames in flight: the server-side queue policy, mirrored on the client
      if (this.inflight < 2 && this.video.videoWidth) {
        const scale = Math.min(1, this.opts.width / this.video.videoWidth)
        canvas.width = Math.round(this.video.videoWidth * scale)
        canvas.height = Math.round(this.video.videoHeight * scale)
        canvas.getContext('2d')!.drawImage(this.video, 0, 0, canvas.width, canvas.height)
        const tUs = (performance.now() - (this.t0 ?? 0)) * 1000
        const blob: Blob | null = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', this.opts.jpegQuality))
        if (blob && this.ws?.readyState === WebSocket.OPEN) {
          this.inflight++
          this.ws.send(header(1, tUs, await blob.arrayBuffer()))
        }
      }
      this.timer = window.setTimeout(tick, period)
    }
    tick()
  }

  private startAudio() {
    if (!this.stream || !this.stream.getAudioTracks().length) return
    this.audioCtx = new AudioContext({ sampleRate: 16000 })
    const src = this.audioCtx.createMediaStreamSource(this.stream)
    // ScriptProcessor is deprecated but universally available and adequate for 16 kHz mono chunks.
    this.audioNode = this.audioCtx.createScriptProcessor(2048, 1, 1)
    this.audioNode.onaudioprocess = (e) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
      const pcm = e.inputBuffer.getChannelData(0)
      const tUs = (performance.now() - (this.t0 ?? 0)) * 1000 - (pcm.length / 16000) * 1e6
      this.ws.send(header(2, tUs, pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength)))
    }
    src.connect(this.audioNode)
    this.audioNode.connect(this.audioCtx.destination)
  }

  stop() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({ type: 'stop' }))
    else this.cleanup()
  }

  private cleanup() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null }
    this.audioNode?.disconnect(); this.audioNode = null
    this.audioCtx?.close(); this.audioCtx = null
    this.stream?.getTracks().forEach((t) => t.stop()); this.stream = null
    this.video.srcObject = null
  }
}

export async function listCameras(): Promise<MediaDeviceInfo[]> {
  const devs = await navigator.mediaDevices.enumerateDevices()
  return devs.filter((d) => d.kind === 'videoinput')
}
