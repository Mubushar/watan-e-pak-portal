/**
 * Live voice agent — OpenAI Realtime API (speech-to-speech) over WebRTC.
 *
 *   1. POST /ai/realtime/session (our backend) → a short-lived client secret; the
 *      backend sets the instructions, reply language, voice and tools.
 *   2. Open a WebRTC call straight to OpenAI with that secret: microphone up, the
 *      agent's voice down, and an "oai-events" data channel for events.
 *   3. The model detects turns itself (you can interrupt it), streams captions of both
 *      sides, and calls our tools; we run them and send the results back.
 */
import { post } from "./api";

export type AgentState = "connecting" | "listening" | "hearing" | "thinking" | "speaking";

export interface AgentHandlers {
  onState: (state: AgentState) => void;
  /** Live caption of the person (`final` once transcription completes). */
  onUserText: (itemId: string, text: string, final: boolean) => void;
  /** Live caption of the agent's speech. */
  onAgentText: (responseId: string, text: string, final: boolean) => void;
  /** Run a tool the agent called; the returned value is sent back to the model. */
  runTool: (name: string, args: Record<string, unknown>, responseId: string) => Promise<unknown>;
  onError: (message: string) => void;
  /** The call ended (by stop() or by the server). */
  onEnd: () => void;
}

interface SessionGrant {
  client_secret: string;
  calls_url: string;
  model: string;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
type ServerEvent = { type: string; [k: string]: any };
/* eslint-enable @typescript-eslint/no-explicit-any */

export class RealtimeAgent {
  private pc: RTCPeerConnection | null = null;
  private dc: RTCDataChannel | null = null;
  private mic: MediaStream | null = null;
  private audio: HTMLAudioElement | null = null;
  private userText = new Map<string, string>();
  private agentText = new Map<string, string>();
  private ended = false;
  muted = false;

  constructor(private h: AgentHandlers) {}

  /** Connect and start talking. Throws with a readable message if it can't. */
  async start(replyLang: "auto" | "en" | "ur"): Promise<void> {
    this.h.onState("connecting");
    const grant = await post<SessionGrant>("/ai/realtime/session", { reply_lang: replyLang }, { timeoutMs: 30_000 });
    if (!grant.client_secret) throw new Error("The server couldn't start a voice session.");

    const pc = new RTCPeerConnection();
    this.pc = pc;
    const audio = document.createElement("audio");
    audio.autoplay = true;
    this.audio = audio;
    pc.ontrack = (e) => {
      audio.srcObject = e.streams[0] ?? null;
    };
    pc.onconnectionstatechange = () => {
      if (["failed", "closed", "disconnected"].includes(pc.connectionState)) this.finish();
    };

    this.mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    for (const track of this.mic.getAudioTracks()) pc.addTrack(track, this.mic);

    const dc = pc.createDataChannel("oai-events");
    this.dc = dc;
    dc.onmessage = (e) => {
      try {
        void this.handle(JSON.parse(e.data as string) as ServerEvent);
      } catch {
        /* ignore malformed events */
      }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const res = await fetch(grant.calls_url, {
      method: "POST",
      body: offer.sdp,
      headers: { Authorization: `Bearer ${grant.client_secret}`, "Content-Type": "application/sdp" },
    });
    if (!res.ok) throw new Error(`OpenAI rejected the voice call (${res.status}).`);
    await pc.setRemoteDescription({ type: "answer", sdp: await res.text() });
  }

  /** Mute / unmute the microphone (the agent keeps the conversation). */
  setMuted(muted: boolean) {
    this.muted = muted;
    this.mic?.getAudioTracks().forEach((t) => (t.enabled = !muted));
  }

  /** Cut the agent off mid-answer so the person can speak. */
  interrupt() {
    this.send({ type: "response.cancel" });
    this.send({ type: "output_audio_buffer.clear" });
  }

  /** Hang up. */
  stop() {
    this.finish();
  }

  private send(event: Record<string, unknown>) {
    if (this.dc?.readyState === "open") this.dc.send(JSON.stringify(event));
  }

  private finish() {
    if (this.ended) return;
    this.ended = true;
    this.mic?.getTracks().forEach((t) => t.stop());
    try {
      this.dc?.close();
      this.pc?.close();
    } catch {
      /* already closed */
    }
    if (this.audio) {
      this.audio.srcObject = null;
      this.audio.remove();
    }
    this.h.onEnd();
  }

  private async handle(ev: ServerEvent) {
    switch (ev.type) {
      case "session.created":
      case "session.updated":
        this.h.onState("listening");
        break;
      case "input_audio_buffer.speech_started":
        this.h.onState("hearing");
        if (ev.item_id && !this.userText.has(ev.item_id)) {
          this.userText.set(ev.item_id, "");
          this.h.onUserText(ev.item_id, "", false);
        }
        break;
      case "input_audio_buffer.speech_stopped":
        this.h.onState("thinking");
        break;
      case "conversation.item.input_audio_transcription.delta": {
        const text = (this.userText.get(ev.item_id) ?? "") + (ev.delta ?? "");
        this.userText.set(ev.item_id, text);
        this.h.onUserText(ev.item_id, text, false);
        break;
      }
      case "conversation.item.input_audio_transcription.completed":
        this.userText.set(ev.item_id, ev.transcript ?? "");
        this.h.onUserText(ev.item_id, (ev.transcript ?? "").trim(), true);
        break;
      case "response.output_audio_transcript.delta": {
        const text = (this.agentText.get(ev.response_id) ?? "") + (ev.delta ?? "");
        this.agentText.set(ev.response_id, text);
        this.h.onAgentText(ev.response_id, text, false);
        break;
      }
      case "response.output_audio_transcript.done":
        this.h.onAgentText(ev.response_id, (ev.transcript ?? this.agentText.get(ev.response_id) ?? "").trim(), true);
        break;
      case "output_audio_buffer.started":
        this.h.onState("speaking");
        break;
      case "output_audio_buffer.stopped":
      case "output_audio_buffer.cleared":
        this.h.onState("listening");
        break;
      case "response.function_call_arguments.done": {
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(ev.arguments || "{}");
        } catch {
          /* keep {} */
        }
        let output: unknown;
        try {
          output = await this.h.runTool(ev.name, args, ev.response_id);
        } catch (e) {
          output = { error: (e as Error).message };
        }
        this.send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: ev.call_id, output: JSON.stringify(output ?? {}) } });
        this.send({ type: "response.create" });
        break;
      }
      case "response.done":
        if (ev.response?.status === "failed") this.h.onError(ev.response?.status_details?.error?.message ?? "The voice agent couldn't answer.");
        break;
      case "error":
        // Cancelling when nothing is playing is harmless; don't alarm the user.
        if (ev.error?.code !== "response_cancel_not_active") this.h.onError(ev.error?.message ?? "Voice agent error");
        break;
    }
  }
}
