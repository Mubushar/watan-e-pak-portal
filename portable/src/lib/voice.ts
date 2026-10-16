/**
 * Voice I/O for the AI assistant, picking the best engine per platform.
 *
 * Speech-to-text (STT)
 *   - Android / iOS:  on-device recognizer via @capacitor-community/speech-recognition
 *   - Browser:        Web Speech API (Chrome, Edge, Safari)
 *   - Desktop app:    records with MediaRecorder and sends the clip to the backend's
 *                     POST /ai/transcribe (needs PORTAL_LLM_BASE_URL on the server),
 *                     because Electron ships without Google's speech service.
 *
 * Text-to-speech (TTS)
 *   - Android / iOS:  native voices via @capacitor-community/text-to-speech
 *   - Elsewhere:      window.speechSynthesis (OS voices on Windows / macOS)
 */
import { SpeechRecognition as NativeStt } from "@capacitor-community/speech-recognition";
import { TextToSpeech as NativeTts } from "@capacitor-community/text-to-speech";
import { get, post } from "./api";
import { isElectron, isNative } from "./platform";

export type SttEngine = "native" | "web" | "server";

export interface ListenOptions {
  lang: string;
  onPartial?: (text: string) => void;
  /** Hard stop after this long (ms). */
  maxMs?: number;
}

export interface ListenSession {
  /** Resolves with the final transcript ("" when nothing was heard). */
  result: Promise<string>;
  /** Finish early and keep what was heard so far. */
  stop: () => void;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
type WebRecognition = any;
const WebSpeech: (new () => WebRecognition) | undefined =
  (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
/* eslint-enable @typescript-eslint/no-explicit-any */

let serverStt: boolean | null = null;
async function serverTranscriptionAvailable(): Promise<boolean> {
  if (serverStt !== null) return serverStt;
  try {
    const caps = await get<{ transcription: boolean }>("/ai/capabilities", undefined, { noFallback: true });
    serverStt = !!caps.transcription;
  } catch {
    serverStt = false;
  }
  return serverStt;
}

/** Which STT engine this device will use, or null when voice input is unavailable. */
export async function sttEngine(): Promise<SttEngine | null> {
  if (isNative) {
    try {
      return (await NativeStt.available()).available ? "native" : null;
    } catch {
      return null;
    }
  }
  if (WebSpeech && !isElectron) return "web";
  if (typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices && (await serverTranscriptionAvailable())) return "server";
  return null;
}

export async function listen(opts: ListenOptions): Promise<ListenSession> {
  const engine = await sttEngine();
  if (engine === "native") return listenNative(opts);
  if (engine === "web") return listenWeb(opts);
  if (engine === "server") return listenServer(opts);
  throw new Error(
    isElectron
      ? "Voice input on desktop needs the server's speech service (PORTAL_LLM_BASE_URL). You can still dictate with your OS (Win + H on Windows, Fn Fn on macOS)."
      : "Voice input isn't supported on this device.",
  );
}

// ---------------------------------------------------------------- native
async function listenNative({ lang, onPartial, maxMs = 20_000 }: ListenOptions): Promise<ListenSession> {
  const perm = await NativeStt.checkPermissions();
  if (perm.speechRecognition !== "granted") {
    const req = await NativeStt.requestPermissions();
    if (req.speechRecognition !== "granted") throw new Error("Microphone / speech permission was denied. Enable it in Settings.");
  }
  let latest = "";
  let done = false;
  let finish: (t: string) => void = () => undefined;
  const result = new Promise<string>((ok) => (finish = ok));
  const end = async () => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    await NativeStt.removeAllListeners().catch(() => undefined);
    finish(latest.trim());
  };
  await NativeStt.addListener("partialResults", ({ matches }) => {
    latest = matches?.[0] ?? latest;
    onPartial?.(latest);
  });
  await NativeStt.addListener("listeningState", ({ status }) => {
    if (status === "stopped") void end();
  });
  const timer = setTimeout(() => void NativeStt.stop().finally(end), maxMs);
  NativeStt.start({ language: lang, maxResults: 1, partialResults: true, popup: false })
    .then((r) => {
      if (r?.matches?.[0]) latest = r.matches[0];
    })
    .catch(() => undefined)
    .finally(() => {
      // iOS resolves start() immediately; Android resolves when speech ends.
    });
  return {
    result,
    stop: () => void NativeStt.stop().catch(() => undefined).finally(end),
  };
}

// ---------------------------------------------------------------- web speech
function listenWeb({ lang, onPartial, maxMs = 20_000 }: ListenOptions): ListenSession {
  const rec: WebRecognition = new WebSpeech!();
  rec.lang = lang;
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;
  let text = "";
  let failure: Error | null = null;
  const result = new Promise<string>((ok, fail) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onresult = (e: any) => {
      text = Array.from(e.results as ArrayLike<{ 0: { transcript: string } }>)
        .map((r) => r[0].transcript)
        .join(" ");
      onPartial?.(text);
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onerror = (e: any) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      failure = new Error(e.error === "not-allowed" ? "Microphone permission was denied." : `Voice input failed (${e.error}).`);
    };
    rec.onend = () => {
      clearTimeout(timer);
      if (failure && !text) fail(failure);
      else ok(text.trim());
    };
  });
  const timer = setTimeout(() => rec.stop(), maxMs);
  rec.start();
  return { result, stop: () => rec.stop() };
}

// ---------------------------------------------------------------- server (desktop)
async function listenServer({ lang, onPartial, maxMs = 15_000 }: ListenOptions): Promise<ListenSession> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
  const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks: Blob[] = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const stopped = new Promise<void>((ok) => (rec.onstop = () => ok()));
  rec.start();
  onPartial?.("Listening… tap the mic again when you're done.");

  // Auto-stop after ~1.5 s of silence once the person has started talking.
  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Uint8Array(analyser.fftSize);
  let heard = false;
  let quietSince = performance.now();
  const vad = setInterval(() => {
    analyser.getByteTimeDomainData(buf);
    const level = Math.max(...buf.map((v) => Math.abs(v - 128)));
    if (level > 12) {
      heard = true;
      quietSince = performance.now();
    } else if (heard && performance.now() - quietSince > 1500) stop();
  }, 120);
  const timer = setTimeout(() => stop(), maxMs);

  function stop() {
    clearInterval(vad);
    clearTimeout(timer);
    if (rec.state !== "inactive") rec.stop();
  }

  const result = (async () => {
    await stopped;
    stream.getTracks().forEach((t) => t.stop());
    void ctx.close();
    const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
    if (blob.size < 2000) return "";
    onPartial?.("Transcribing…");
    const audio_base64 = await blobToBase64(blob);
    const r = await post<{ text: string }>("/ai/transcribe", { audio_base64, mime_type: blob.type, language: lang.slice(0, 2) }, { timeoutMs: 60_000 });
    return (r.text ?? "").trim();
  })();
  return { result, stop };
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((ok, fail) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] ?? "");
    r.onerror = () => fail(r.error);
    r.readAsDataURL(blob);
  });
}

// ---------------------------------------------------------------- text-to-speech
/** Strip markdown and long lists so replies sound natural when read aloud. */
export function speakable(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_`#>]/g, "")
    .replace(/\bPKR\b/g, "rupees")
    .replace(/\n{2,}/g, ". ")
    .replace(/\n/g, ", ")
    .slice(0, 600);
}

export function canSpeak(): boolean {
  return isNative || "speechSynthesis" in window;
}

let speaking = false;
export function isSpeaking() {
  return speaking;
}

export async function speak(text: string, lang: string): Promise<void> {
  const say = speakable(text);
  if (!say.trim()) return;
  await stopSpeaking();
  speaking = true;
  try {
    if (isNative) {
      await NativeTts.speak({ text: say, lang, rate: 1.0, pitch: 1.0, volume: 1.0, category: "playback" });
      return;
    }
    if (!("speechSynthesis" in window)) return;
    await new Promise<void>((ok) => {
      const u = new SpeechSynthesisUtterance(say);
      u.lang = lang;
      const voices = speechSynthesis.getVoices();
      const base = lang.slice(0, 2);
      u.voice = voices.find((v) => v.lang === lang) ?? voices.find((v) => v.lang.startsWith(base)) ?? null;
      u.rate = 1.02;
      u.onend = () => ok();
      u.onerror = () => ok();
      speechSynthesis.speak(u);
    });
  } finally {
    speaking = false;
  }
}

export async function stopSpeaking(): Promise<void> {
  speaking = false;
  if (isNative) await NativeTts.stop().catch(() => undefined);
  else if ("speechSynthesis" in window) speechSynthesis.cancel();
}
