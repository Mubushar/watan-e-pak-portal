/**
 * Live conversation feed over `WS /ws/messaging/{id}?user_id=`.
 *
 * - Calls `onEvent` for every server event (except ready/pong keep-alives).
 * - Reconnects with exponential backoff (1s → 30s).
 * - After 3 consecutive failures without ever opening it reports `mode: "polling"`
 *   so the caller can fall back to periodic refetching (10 s).
 */
import { useEffect, useRef, useState } from "react";
import { wsUrl } from "@/lib/api";

export type LiveMode = "connecting" | "live" | "polling" | "off";

export interface LiveEvent {
  event: string;
  [k: string]: unknown;
}

export function useLiveConversation(conversationId: string | null | undefined, userId: string | null | undefined, onEvent: (e: LiveEvent) => void): LiveMode {
  const [mode, setMode] = useState<LiveMode>("off");
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    if (!conversationId || !userId || typeof WebSocket === "undefined") {
      setMode("off");
      return;
    }
    let ws: WebSocket | null = null;
    let closed = false;
    let attempt = 0;
    let failures = 0;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;

    const connect = () => {
      if (closed) return;
      setMode((m) => (m === "polling" ? m : "connecting"));
      let opened = false;
      try {
        ws = new WebSocket(wsUrl(`/ws/messaging/${conversationId}`, { user_id: userId }));
      } catch {
        schedule(false);
        return;
      }
      ws.onopen = () => {
        opened = true;
        attempt = 0;
        failures = 0;
        setMode("live");
        ping = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send("ping"), 25_000);
      };
      ws.onmessage = (m) => {
        try {
          const ev = JSON.parse(String(m.data)) as LiveEvent;
          if (ev.event === "pong" || ev.event === "ready") return;
          cb.current(ev);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = (ev) => {
        if (ping) clearInterval(ping);
        if (closed) return;
        if (ev.code === 4403) {
          setMode("polling");
          return;
        }
        schedule(opened);
      };
      ws.onerror = () => ws?.close();
    };

    const schedule = (hadOpened: boolean) => {
      if (!hadOpened) failures += 1;
      if (failures >= 3) setMode("polling");
      else setMode("connecting");
      const delay = Math.min(30_000, 1000 * 2 ** attempt);
      attempt += 1;
      retry = setTimeout(connect, delay);
    };

    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      if (ping) clearInterval(ping);
      ws?.close();
    };
  }, [conversationId, userId]);

  return mode;
}
