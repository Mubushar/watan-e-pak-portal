/**
 * Voice for the AI assistant, through our backend (API keys never ship in the app):
 *   - Voice notes / dictation: record with the microphone → POST /ai/transcribe
 *     (OpenAI speech-to-text; Urdu comes back in Urdu script, English in English).
 *   - Spoken replies: POST /ai/speak (OpenAI text-to-speech) → play the clip.
 *   - Live conversation: lib/realtime.ts (OpenAI Realtime over WebRTC), or
 *     lib/gemini-live.ts (Gemini Live over a WebSocket) when the backend runs with
 *     VOICE_PROVIDER=gemini for testing.
 * Works the same on Android, iOS, Windows, macOS and the web.
 */
import { get, post } from "./api";

export interface ServerVoice {
  /** Speech-to-text available (voice notes). */
  stt: boolean;
  /** Text-to-speech available (voice-note replies). */
  tts: boolean;
  /** Live voice agent available. */
  realtime: boolean;
  provider: "openai" | null;
  /** Which service runs the live conversation. */
  liveProvider: "openai" | "gemini" | null;
}

const NO_SERVER_VOICE: ServerVoice = { stt: false, tts: false, realtime: false, provider: null, liveProvider: null };
let voiceCaps: { at: number; value: ServerVoice } | null = null;

/** What the backend offers for voice (cached for a minute). */
export async function serverVoice(): Promise<ServerVoice> {
  if (voiceCaps && Date.now() - voiceCaps.at < 60_000) return voiceCaps.value;
  let value = NO_SERVER_VOICE;
  try {
    const caps = await get<{ voice?: Partial<ServerVoice> & { live_provider?: "openai" | "gemini" | null } }>("/ai/capabilities", undefined, { noFallback: true });
    const v = caps.voice;
    value = { stt: !!v?.stt, tts: !!v?.tts, realtime: !!v?.realtime, provider: v?.provider ?? null, liveProvider: v?.live_provider ?? (v?.realtime ? "openai" : null) };
  } catch {
    /* backend unreachable */
  }
  voiceCaps = { at: Date.now(), value };
  return value;
}

/** Forget cached server voice support (e.g. after changing the server URL). */
export function resetServerVoice() {
  voiceCaps = null;
}

export const NOT_CONFIGURED = "Voice needs OpenAI on the server — add OPENAI_API_KEY to backend/.env and restart it.";
export const LIVE_NOT_CONFIGURED =
  "The live voice agent isn't set up on the server — add OPENAI_API_KEY (or VOICE_PROVIDER=gemini with GEMINI_API_KEY) to backend/.env and restart it.";

export const canRecord = () => typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

// ---------------------------------------------------------------- recording

export interface ListenOptions {
  onPartial?: (text: string) => void;
  /** Hard stop after this long (ms). */
  maxMs?: number;
  /** Stop by itself after a pause in speech (dictation); voice notes wait for stop(). */
  autoStop?: boolean;
}

export interface Recording {
  /** What was said ("" if nothing was heard or it was cancelled). */
  text: string;
  /** The person's own recording, for playback in a voice-note bubble. */
  audioUrl?: string;
  durationMs: number;
}

export interface RecordingSession {
  result: Promise<Recording>;
  /** Finish and transcribe. */
  stop: () => void;
  /** Throw the recording away. */
  cancel: () => void;
}

export type VoiceNoteSession = RecordingSession;
export type ListenSession = RecordingSession;

/**
 * Record from the microphone and transcribe with OpenAI. With `autoStop` it ends ~1.5 s
 * after the person stops talking (or after 8 s of silence); otherwise it waits for stop().
 */
export async function record({ onPartial, maxMs = 120_000, autoStop = false }: ListenOptions = {}): Promise<RecordingSession> {
  if (!(await serverVoice()).stt) throw new Error(NOT_CONFIGURED);
  if (!canRecord()) throw new Error("This device can't record audio.");
  const started = performance.now();
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
  const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks: Blob[] = [];
  let cancelled = false;
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const stopped = new Promise<void>((ok) => (rec.onstop = () => ok()));
  rec.start();

  // Voice-activity detection: lets dictation stop itself and skips silent clips.
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Uint8Array(analyser.fftSize);
  let heard = false;
  let quietSince = performance.now();
  const vad = setInterval(() => {
    analyser.getByteTimeDomainData(buf);
    let level = 0;
    for (const v of buf) level = Math.max(level, Math.abs(v - 128));
    if (level > 12) {
      heard = true;
      quietSince = performance.now();
    } else if (autoStop && heard && performance.now() - quietSince > 1500) finish();
    else if (autoStop && !heard && performance.now() - quietSince > 8000) finish();
  }, 120);
  const timer = setTimeout(() => finish(), maxMs);

  function finish() {
    clearInterval(vad);
    clearTimeout(timer);
    if (rec.state !== "inactive") rec.stop();
  }

  const result = (async (): Promise<Recording> => {
    await stopped;
    stream.getTracks().forEach((t) => t.stop());
    void ctx.close();
    const durationMs = performance.now() - started;
    const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
    // Don't send silence to OpenAI (it costs a transcription and returns nothing).
    if (cancelled || !heard || blob.size < 1500) return { text: "", durationMs };
    onPartial?.("…");
    const audioUrl = URL.createObjectURL(blob);
    const r = await post<{ text: string }>("/ai/transcribe", { audio_base64: await blobToBase64(blob), mime_type: blob.type }, { timeoutMs: 90_000 });
    return { text: (r.text ?? "").trim(), audioUrl, durationMs };
  })();

  return {
    result,
    stop: finish,
    cancel: () => {
      cancelled = true;
      finish();
    },
  };
}

/** Dictation: listen until the person pauses, then return the text. */
export async function listen(opts: Omit<ListenOptions, "autoStop"> = {}) {
  return record({ ...opts, autoStop: true, maxMs: opts.maxMs ?? 30_000 });
}

/** A voice note: record until stop(), keep the audio, transcribe. */
export async function recordVoiceNote(onPartial?: (text: string) => void) {
  return record({ onPartial, autoStop: false, maxMs: 120_000 });
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((ok, fail) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] ?? "");
    r.onerror = () => fail(r.error);
    r.readAsDataURL(blob);
  });
}

// ---------------------------------------------------------------- speaking

/** Strip markdown and list separators so replies sound natural when read aloud. */
export function speakable(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_`#>]/g, "")
    .replace(/\s*·\s*/g, ", ")
    .replace(/\bPKR\b/g, "rupees")
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, ", ")
    .slice(0, 1200);
}

export function canSpeak(): boolean {
  return !!voiceCaps?.value.tts;
}

/** Turn text into an OpenAI voice clip (data URL), or null if voice isn't available. */
export async function synthesize(text: string, lang: string): Promise<string | null> {
  const say = speakable(text);
  if (!say.trim() || !(await serverVoice()).tts) return null;
  try {
    const r = await post<{ audio_base64: string; mime_type: string }>("/ai/speak", { text: say, language: lang }, { timeoutMs: 60_000 });
    return `data:${r.mime_type};base64,${r.audio_base64}`;
  } catch {
    return null;
  }
}

let player: HTMLAudioElement | null = null;
let speaking = false;

export function isSpeaking() {
  return speaking;
}

/** Play an audio clip; resolves when it ends or is stopped. */
export async function playAudio(url: string): Promise<void> {
  await stopSpeaking();
  speaking = true;
  const audio = new Audio(url);
  player = audio;
  try {
    await new Promise<void>((ok, fail) => {
      audio.onended = () => ok();
      audio.onpause = () => ok();
      audio.onerror = () => fail(new Error("Couldn't play the audio."));
      audio.play().catch(fail);
    });
  } finally {
    if (player === audio) player = null;
    speaking = false;
  }
}

export type SpeakResult = "spoken" | "unavailable";

/** Speak text with the OpenAI voice. */
export async function speak(text: string, lang: string): Promise<SpeakResult> {
  const url = await synthesize(text, lang);
  if (!url) return "unavailable";
  await playAudio(url);
  return "spoken";
}

export async function stopSpeaking(): Promise<void> {
  speaking = false;
  player?.pause();
}
