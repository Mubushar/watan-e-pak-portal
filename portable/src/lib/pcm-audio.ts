/**
 * Raw PCM audio for WebSocket voice APIs (Gemini Live):
 *   - MicStream: microphone → 16-bit little-endian mono PCM chunks at a fixed rate (16 kHz).
 *   - PcmPlayer: queued playback of 16-bit PCM chunks (24 kHz) without gaps, with a
 *     `clear()` for barge-in (the person interrupts the agent).
 * Uses an AudioWorklet (loaded from a Blob URL, so no extra file to ship) and resamples in
 * the worklet when the device won't open an AudioContext at the requested rate.
 */

const CAPTURE_WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.target = options.processorOptions.targetRate;
    this.ratio = sampleRate / this.target;
    this.pos = 0;
    this.buf = new Int16Array(Math.round(this.target / 10)); // 100 ms chunks
    this.n = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    // Linear-interpolation resample to the target rate.
    while (this.pos < ch.length) {
      const i = Math.floor(this.pos);
      const f = this.pos - i;
      const a = ch[i];
      const b = i + 1 < ch.length ? ch[i + 1] : a;
      const s = Math.max(-1, Math.min(1, a + (b - a) * f));
      this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.n === this.buf.length) {
        this.port.postMessage(this.buf.buffer, [this.buf.buffer]);
        this.buf = new Int16Array(this.buf.length);
        this.n = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= ch.length;
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
`;

let workletUrl: string | null = null;
function captureWorkletUrl(): string {
  workletUrl ??= URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "application/javascript" }));
  return workletUrl;
}

export function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

export function fromBase64(b64: string): ArrayBuffer {
  const s = atob(b64);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out.buffer;
}

/** Microphone → PCM16 chunks (~100 ms each) at `rate` Hz. */
export class MicStream {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  muted = false;

  constructor(
    private onChunk: (pcm: ArrayBuffer) => void,
    private rate = 16_000,
  ) {}

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    // Ask for the target rate; browsers that refuse fall back to the device rate and the worklet resamples.
    try {
      this.ctx = new AudioContext({ sampleRate: this.rate });
    } catch {
      this.ctx = new AudioContext();
    }
    await this.ctx.audioWorklet.addModule(captureWorkletUrl());
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "pcm-capture", { processorOptions: { targetRate: this.rate } });
    this.node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      if (!this.muted) this.onChunk(e.data);
    };
    src.connect(this.node);
    // The worklet must be pulled by the graph; route it to a silent gain.
    const sink = this.ctx.createGain();
    sink.gain.value = 0;
    this.node.connect(sink).connect(this.ctx.destination);
  }

  stop() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.node?.disconnect();
    void this.ctx?.close().catch(() => undefined);
    this.stream = null;
    this.node = null;
    this.ctx = null;
  }
}

/** Gap-free playback of PCM16 mono chunks; `onIdle` fires when the queue runs dry. */
export class PcmPlayer {
  private ctx: AudioContext;
  private next = 0;
  private sources = new Set<AudioBufferSourceNode>();

  constructor(
    private rate = 24_000,
    private onPlaying?: (playing: boolean) => void,
  ) {
    this.ctx = new AudioContext();
  }

  get playing(): boolean {
    return this.sources.size > 0;
  }

  play(pcm: ArrayBuffer) {
    if (this.ctx.state === "suspended") void this.ctx.resume();
    const ints = new Int16Array(pcm);
    if (!ints.length) return;
    const buf = this.ctx.createBuffer(1, ints.length, this.rate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < ints.length; i++) ch[i] = ints[i]! / 0x8000;
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);
    const at = Math.max(this.ctx.currentTime + 0.03, this.next);
    src.start(at);
    this.next = at + buf.duration;
    const wasIdle = !this.sources.size;
    this.sources.add(src);
    if (wasIdle) this.onPlaying?.(true);
    src.onended = () => {
      this.sources.delete(src);
      if (!this.sources.size) this.onPlaying?.(false);
    };
  }

  /** Stop everything queued (the person interrupted). */
  clear() {
    for (const s of this.sources) {
      s.onended = null;
      try {
        s.stop();
      } catch {
        /* not started yet */
      }
    }
    const had = this.sources.size > 0;
    this.sources.clear();
    this.next = 0;
    if (had) this.onPlaying?.(false);
  }

  close() {
    this.clear();
    void this.ctx.close().catch(() => undefined);
  }
}
