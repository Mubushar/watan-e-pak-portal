/**
 * Record a voice note in the browser (MediaRecorder) and hand it back as base64 for the backend
 * (POST /crm/ai/note, /crm/ai/ask). Stops by itself after `maxSeconds`.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export interface Recording {
  base64: string;
  mime: string;
  seconds: number;
}

function pickMime(): string {
  const options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return options.find((m) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(m)) ?? "";
}

export function useRecorder(onDone: (r: Recording) => void, maxSeconds = 120) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const started = useRef(0);
  const done = useRef(onDone);
  done.current = onDone;

  const stop = useCallback(() => {
    if (rec.current && rec.current.state !== "inactive") rec.current.stop();
  }, []);

  const start = useCallback(async () => {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("This browser can't record audio");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = pickMime();
      const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (timer.current) clearInterval(timer.current);
        setRecording(false);
        const blob = new Blob(chunks, { type: r.mimeType || mime || "audio/webm" });
        const secs = Math.round((Date.now() - started.current) / 1000);
        if (!blob.size) return;
        const reader = new FileReader();
        reader.onloadend = () => done.current({ base64: String(reader.result), mime: blob.type.split(";")[0] || "audio/webm", seconds: secs });
        reader.readAsDataURL(blob);
      };
      rec.current = r;
      started.current = Date.now();
      setSeconds(0);
      r.start();
      setRecording(true);
      timer.current = setInterval(() => {
        const s = Math.round((Date.now() - started.current) / 1000);
        setSeconds(s);
        if (s >= maxSeconds) r.stop();
      }, 250);
    } catch {
      setError("Microphone permission was denied");
    }
  }, [maxSeconds]);

  useEffect(() => () => stop(), [stop]);

  return { recording, seconds, error, start, stop, toggle: () => (recording ? stop() : void start()) };
}
