/**
 * Live voice agent — Google Gemini Live API (testing alternative to OpenAI Realtime).
 *
 * Used when the backend runs with VOICE_PROVIDER=gemini (GET /ai/capabilities reports
 * voice.live_provider "gemini"). Same contract as lib/realtime.ts so the Assistant screen
 * doesn't care which one it talks to:
 *   1. POST /ai/realtime/session → a single-use ephemeral token, the WebSocket URL and the
 *      session `setup` (instructions, voice, tools) built by the backend.
 *   2. Open the WebSocket, send `setup`, wait for `setupComplete`.
 *   3. Stream the microphone up as 16 kHz PCM; play the agent's 24 kHz PCM; Gemini detects
 *      turns (and barge-in) itself, sends captions of both sides, and calls our tools.
 * Long calls: when Gemini announces `goAway` the client reconnects with the latest
 * session-resumption handle, so the conversation carries on.
 */
import { post } from "./api";
import type { AgentHandlers } from "./realtime";
import { fromBase64, MicStream, PcmPlayer, toBase64 } from "./pcm-audio";

interface GeminiGrant {
  provider: "gemini";
  token: string;
  ws_url: string;
  setup: Record<string, unknown>;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
type ServerMsg = { [k: string]: any };
/* eslint-enable @typescript-eslint/no-explicit-any */

export class GeminiLiveAgent {
  private ws: WebSocket | null = null;
  private mic: MicStream | null = null;
  private player: PcmPlayer | null = null;
  private grant: GeminiGrant | null = null;
  private resumeHandle: string | null = null;
  private reconnecting = false;
  private ended = false;
  private ready = false;
  /** Caption ids: one per user turn and one per agent "segment" (split at tool calls). */
  private seq = 0;
  private userId: string | null = null;
  private userText = "";
  private segId: string | null = null;
  private segText = "";
  /** Reconnects so far (goAway / dropped connection), capped so a failing session can't loop. */
  private resumes = 0;
  /** Ignore the rest of an answer the person cut off with the stop button. */
  private dropAudio = false;
  muted = false;

  constructor(private h: AgentHandlers) {}

  /** Connect and start talking. Throws with a readable message if it can't. */
  async start(replyLang: "auto" | "en" | "ur"): Promise<void> {
    this.h.onState("connecting");
    // Create the audio output inside the tap that started the call (autoplay rules).
    this.player = new PcmPlayer(24_000, (playing) => {
      if (!this.ended && this.ready) this.h.onState(playing ? "speaking" : "listening");
    });
    const grant = await post<GeminiGrant>("/ai/realtime/session", { reply_lang: replyLang }, { timeoutMs: 30_000 });
    if (grant.provider !== "gemini" || !grant.token) throw new Error("The server couldn't start a voice session.");
    this.grant = grant;
    await this.connect();
    this.mic = new MicStream((pcm) => this.send({ realtimeInput: { audio: { data: toBase64(pcm), mimeType: "audio/pcm;rate=16000" } } }));
    await this.mic.start();
  }

  /** Open (or re-open, after goAway) the WebSocket and finish the setup handshake. */
  private connect(): Promise<void> {
    const g = this.grant!;
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(`${g.ws_url}?access_token=${encodeURIComponent(g.token)}`);
      ws.binaryType = "arraybuffer";
      this.ws = ws;
      let settled = false;
      ws.onopen = () => {
        const setup = this.resumeHandle ? { ...g.setup, sessionResumption: { handle: this.resumeHandle } } : g.setup;
        ws.send(JSON.stringify({ setup }));
      };
      ws.onmessage = (e) => {
        const raw = typeof e.data === "string" ? e.data : new TextDecoder().decode(e.data as ArrayBuffer);
        let msg: ServerMsg;
        try {
          msg = JSON.parse(raw);
        } catch {
          return;
        }
        if (msg.setupComplete !== undefined && !settled) {
          settled = true;
          this.ready = true;
          if (!this.reconnecting) this.h.onState("listening");
          this.reconnecting = false;
          resolve();
          return;
        }
        void this.handle(msg);
      };
      ws.onerror = () => {
        if (!settled) {
          settled = true;
          reject(new Error("Couldn't connect to Gemini Live."));
        }
      };
      ws.onclose = (e) => {
        if (this.ws !== ws) return; // an old socket we replaced
        if (!settled) {
          settled = true;
          reject(new Error(e.reason ? `Gemini closed the voice session: ${e.reason}` : "Gemini closed the voice session."));
          return;
        }
        if (this.ended || this.reconnecting) return;
        if (this.resumeHandle) return void this.resume();
        if (e.code !== 1000) this.h.onError(e.reason ? `Voice session ended: ${e.reason}` : "The voice session ended.");
        this.finish();
      };
    });
  }

  /** Reconnect with the session-resumption handle (Gemini drops connections after ~10 min). */
  private resume() {
    if (this.reconnecting || this.ended || !this.resumeHandle) return;
    if (++this.resumes > 5) {
      this.h.onError("The voice session dropped — start a new conversation.");
      return this.finish();
    }
    this.reconnecting = true;
    this.ready = false;
    const old = this.ws;
    this.ws = null;
    try {
      old?.close();
    } catch {
      /* already closed */
    }
    this.connect().catch((e: Error) => {
      this.reconnecting = false;
      this.h.onError(e.message);
      this.finish();
    });
  }

  /** Mute / unmute the microphone (the agent keeps the conversation). */
  setMuted(muted: boolean) {
    this.muted = muted;
    if (this.mic) this.mic.muted = muted;
    if (muted) this.send({ realtimeInput: { audioStreamEnd: true } });
  }

  /** Cut the agent off mid-answer so the person can speak. */
  interrupt() {
    this.player?.clear();
    this.dropAudio = true;
  }

  /** Hang up. */
  stop() {
    this.finish();
  }

  private send(msg: Record<string, unknown>) {
    if (this.ready && this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  private finish() {
    if (this.ended) return;
    this.ended = true;
    this.mic?.stop();
    this.player?.close();
    try {
      this.ws?.close(1000);
    } catch {
      /* already closed */
    }
    this.ws = null;
    this.h.onEnd();
  }

  // ------------------------------------------------------------------ captions
  private userTurn(): string {
    if (!this.userId) {
      this.userId = `g${++this.seq}`;
      this.userText = "";
      this.h.onUserText(this.userId, "", false);
    }
    return this.userId;
  }

  private closeUserTurn() {
    if (!this.userId) return;
    this.h.onUserText(this.userId, this.userText.trim(), true);
    this.userId = null;
  }

  private segment(): string {
    if (!this.segId) {
      this.segId = `g${++this.seq}`;
      this.segText = "";
    }
    return this.segId;
  }

  private closeSegment() {
    if (!this.segId) return;
    const id = this.segId;
    if (this.segText) this.h.onAgentText(id, this.segText.trim(), true);
    this.segId = null;
    this.h.onResponseDone?.(id);
  }

  // ------------------------------------------------------------------ server messages
  private async handle(msg: ServerMsg) {
    if (msg.sessionResumptionUpdate?.resumable && msg.sessionResumptionUpdate.newHandle) {
      this.resumeHandle = msg.sessionResumptionUpdate.newHandle;
    }
    if (msg.goAway) {
      this.resume();
      return;
    }
    if (msg.toolCall) {
      await this.toolCall(msg.toolCall.functionCalls ?? []);
      return;
    }
    const sc = msg.serverContent;
    if (!sc) return;

    if (sc.inputTranscription?.text) {
      const id = this.userTurn();
      this.userText += sc.inputTranscription.text;
      this.h.onUserText(id, this.userText, false);
      if (!this.player?.playing) this.h.onState("hearing");
    }
    if (sc.interrupted) {
      // The person started talking over the agent: stop its voice and close its line.
      this.player?.clear();
      this.dropAudio = false;
      this.closeSegment();
      this.h.onState("hearing");
    }
    for (const part of sc.modelTurn?.parts ?? []) {
      if (part.inlineData?.data && !this.dropAudio) {
        this.closeUserTurn();
        this.segment();
        this.player?.play(fromBase64(part.inlineData.data));
      }
    }
    if (sc.outputTranscription?.text && !this.dropAudio) {
      this.closeUserTurn();
      const id = this.segment();
      this.segText += sc.outputTranscription.text;
      this.h.onAgentText(id, this.segText, false);
    }
    if (sc.turnComplete) {
      this.closeUserTurn();
      this.closeSegment();
      this.dropAudio = false;
      if (!this.player?.playing) this.h.onState("listening");
    }
  }

  private async toolCall(calls: { id?: string; name: string; args?: Record<string, unknown> }[]) {
    this.closeUserTurn();
    const seg = this.segment();
    this.h.onState("thinking");
    const functionResponses = [];
    for (const c of calls) {
      let output: unknown;
      try {
        output = await this.h.runTool(c.name, c.args ?? {}, seg);
      } catch (e) {
        output = { error: (e as Error).message };
      }
      functionResponses.push({ id: c.id, name: c.name, response: { result: output ?? {} } });
    }
    this.send({ toolResponse: { functionResponses } });
    // What the agent says next (with the results) is a new segment: the answer the cards attach to.
    this.closeSegment();
  }
}
