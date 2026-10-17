/**
 * Admin → System: which outside services the backend has wired up (no secrets are exposed).
 *   GET /ai/capabilities   OpenAI chat + voice models
 *   GET /auth/config       OTP delivery providers (e-mail / SMS)
 *   GET /ads/config        AdSense (web) and AdMob (apps)
 *   GET /geo/summary       places / areas / population data
 *   GET /masterplans       DHA master plans built on this server
 */
import type { ReactNode } from "react";
import { Bot, Map as MapIcon, Megaphone, MessageSquareText, Plug } from "lucide-react";
import type { AdConfig } from "@/types";
import { useApi } from "@/hooks/useApi";
import { num } from "@/lib/format";
import { Badge, Card, CardBody, CardHeader, Skeleton } from "@/components/ui";

interface AiCaps {
  chat_mode: "local" | "upstream";
  chat_model: string;
  voice: { provider: string | null; stt_model: string | null; tts_model: string | null; realtime_model: string | null; voice: string | null };
}

function Row({ icon, title, ok, children }: { icon: ReactNode; title: string; ok: boolean | undefined; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-black/5 p-3 dark:border-white/10">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700 dark:bg-white/5 dark:text-brand-200">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold">{title}</p>
          {ok === undefined ? null : <Badge tone={ok ? "green" : "gray"}>{ok ? "Connected" : "Not set up"}</Badge>}
        </div>
        <div className="mt-1 text-xs text-ink-mute">{children}</div>
      </div>
    </div>
  );
}

export function IntegrationsCard() {
  const opts = { staleTime: 5 * 60_000, retry: false } as const;
  const ai = useApi<AiCaps>("/ai/capabilities", undefined, opts);
  const auth = useApi<{ delivery?: { email: string; sms: string } }>("/auth/config", undefined, opts);
  const ads = useApi<AdConfig & { admob: { testing: boolean } | null }>("/ads/config", undefined, opts);
  const geo = useApi<{ places: number; areas: number; population_cells: number }>("/geo/summary", undefined, opts);
  const plans = useApi<{ count: number; plans: { name: string }[] }>("/masterplans", undefined, opts);
  const loading = ai.isLoading || auth.isLoading;
  const d = auth.data?.delivery;
  const realOtp = !!d && (d.email !== "simulated" || d.sms !== "simulated");

  return (
    <Card>
      <CardHeader title="Integrations" subtitle="Outside services this backend is using" icon={<Plug className="h-5 w-5" />} />
      <CardBody className="grid gap-3 md:grid-cols-2">
        {loading ? (
          <Skeleton className="h-40 md:col-span-2" />
        ) : (
          <>
            <Row icon={<Bot className="h-4 w-4" />} title="AI assistant (OpenAI)" ok={ai.data ? ai.data.chat_mode === "upstream" : undefined}>
              {ai.data?.chat_mode === "upstream" ? (
                <>
                  Chat: <b>{ai.data.chat_model}</b>
                  {ai.data.voice.stt_model && <> · speech-to-text {ai.data.voice.stt_model}</>}
                  {ai.data.voice.realtime_model && <> · live voice {ai.data.voice.realtime_model}</>}
                </>
              ) : (
                "Local answers from portal data. Set OPENAI_API_KEY in backend/.env for the tool-using assistant and voice."
              )}
            </Row>
            <Row icon={<MessageSquareText className="h-4 w-4" />} title="Sign-in codes (OTP)" ok={d ? realOtp : undefined}>
              {d ? (
                <>
                  E-mail: <b>{d.email}</b> · SMS: <b>{d.sms}</b>
                  {!realOtp && " — codes are shown on screen (test mode)"}
                </>
              ) : (
                "—"
              )}
            </Row>
            <Row icon={<Megaphone className="h-4 w-4" />} title="Ad networks" ok={ads.data ? !!(ads.data.adsense || (ads.data.admob && !ads.data.admob.testing)) : undefined}>
              {ads.data ? (
                <>
                  AdSense (web): <b>{ads.data.adsense ? `${Object.keys(ads.data.adsense.slots).length} unit(s)` : "off"}</b> · AdMob (apps): <b>{ads.data.admob ? (ads.data.admob.testing ? "test ads" : "live") : "off"}</b>
                </>
              ) : (
                "—"
              )}
            </Row>
            <Row icon={<MapIcon className="h-4 w-4" />} title="Places & master plans" ok={geo.data || plans.data ? (geo.data?.places ?? 0) > 0 || (plans.data?.count ?? 0) > 0 : undefined}>
              {geo.data ? (
                <>
                  {num(geo.data.places)} places · {num(geo.data.areas)} areas · {num(geo.data.population_cells)} population cells
                </>
              ) : (
                "Place data not installed"
              )}
              <br />
              {plans.data?.count ? `${plans.data.count} DHA master plan(s): ${plans.data.plans.map((p) => p.name).join(", ")}` : "No master plans built (run backend/masterplans/build_masterplans.py)"}
            </Row>
          </>
        )}
      </CardBody>
    </Card>
  );
}
