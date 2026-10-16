import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Bot, LineChart, MapPinned, ShieldCheck } from "lucide-react";
import { HERO } from "@/lib/images";
import { Logo } from "@/components/ui";

const PERKS: [typeof Bot, string][] = [
  [Bot, "Voice & chat AI assistant for buying, selling and investing"],
  [MapPinned, "Verified listings across Pakistan's top cities and schemes"],
  [LineChart, "Live prices, trends and investment insights"],
  [ShieldCheck, "Sign in with a one-time code — no password needed"],
];

/** Split-screen frame (portal AuthShell) that collapses to a hero header on phones. */
export function AuthLayout({ title, subtitle, children, back = true }: { title: ReactNode; subtitle?: ReactNode; children: ReactNode; back?: boolean }) {
  const nav = useNavigate();
  return (
    <div className="min-h-full lg:grid lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-brand-950 p-10 text-white lg:flex lg:flex-col">
        <img src={HERO.panorama} alt="" className="absolute inset-0 h-full w-full object-cover opacity-50" />
        <div className="absolute inset-0 bg-gradient-to-t from-brand-950 via-brand-950/70 to-brand-950/20" />
        <div className="drag relative">
          <Logo light />
        </div>
        <div className="relative mt-auto">
          <h2 className="font-display text-4xl font-bold leading-tight">
            Your land.
            <br />
            Our intelligence.
            <br />
            <span className="text-gradient">A brighter Pakistan.</span>
          </h2>
          <ul className="mt-8 space-y-3 text-sm text-white/85">
            {PERKS.map(([Icon, t]) => (
              <li key={t} className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
                  <Icon className="h-4 w-4 text-gold-300" />
                </span>
                {t}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="flex min-h-full flex-col">
        <div className="pt-safe relative overflow-hidden bg-brand-gradient text-white lg:hidden">
          <img src={HERO.panorama} alt="" className="absolute inset-0 h-full w-full object-cover opacity-30" />
          <div className="absolute inset-0 bg-mesh" />
          <div className="relative flex items-center justify-between px-4 pb-10 pt-3">
            {back ? (
              <button onClick={() => nav(-1)} className="btn btn-ghost btn-icon -ms-2 text-white hover:bg-white/10" aria-label="Back">
                <ArrowLeft className="h-5 w-5" />
              </button>
            ) : (
              <span />
            )}
            <Logo light compact />
            <span className="w-10" />
          </div>
        </div>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="pb-safe relative -mt-6 flex-1 rounded-t-[1.75rem] bg-[#f6f8f6] px-5 pt-7 lg:mt-0 lg:flex lg:items-center lg:justify-center lg:rounded-none dark:bg-[#07130d]"
        >
          <div className="mx-auto w-full max-w-md pb-10">
            {back && (
              <button onClick={() => nav(-1)} className="mb-6 hidden items-center gap-1 text-sm font-semibold text-ink-mute hover:text-ink lg:inline-flex">
                <ArrowLeft className="h-4 w-4" /> Back
              </button>
            )}
            <h1 className="font-display text-3xl font-bold text-brand-900 dark:text-white">{title}</h1>
            {subtitle && <p className="mt-2 text-ink-mute dark:text-slate-400">{subtitle}</p>}
            <div className="mt-7">{children}</div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

/** Development helper: the backend returns the code when PORTAL_AUTH_EXPOSE_OTP is on. */
export function DevOtpHint({ code, onUse }: { code?: string | null; onUse: (c: string) => void }) {
  if (!code) return null;
  return (
    <div className="mt-3 flex items-center justify-between gap-2 rounded-xl border border-dashed border-gold-300 bg-gold-50 px-3 py-2 text-xs text-gold-800 dark:border-gold-500/30 dark:bg-gold-500/10 dark:text-gold-200">
      <span>
        Dev mode — code sent: <b className="font-mono text-sm">{code}</b>
      </span>
      <button type="button" className="font-semibold underline" onClick={() => onUse(code)}>
        Use it
      </button>
    </div>
  );
}

/** "Resend code" with the backend's 30-second cooldown shown as a countdown. */
export function ResendButton({ seconds, onResend }: { seconds: number; onResend: () => void }) {
  return (
    <button type="button" disabled={seconds > 0} onClick={onResend} className="text-sm font-semibold text-brand-700 disabled:text-ink-mute dark:text-brand-300">
      {seconds > 0 ? `Resend code in ${seconds}s` : "Resend code"}
    </button>
  );
}

// ------------------------------------------------------------------ identifier helpers
export type Channel = "mobile" | "email";

/** "0300 1234567", "3001234567", "+92 300 1234567" → "+923001234567" (PK numbers). */
export function toE164(raw: string): string {
  let d = raw.replace(/[^\d+]/g, "");
  if (d.startsWith("+")) return d;
  if (d.startsWith("00")) return `+${d.slice(2)}`;
  if (d.startsWith("92") && d.length >= 12) return `+${d}`;
  if (d.startsWith("0")) d = d.slice(1);
  return `+92${d}`;
}

export function validIdentifier(channel: Channel, v: string): boolean {
  if (channel === "email") return /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(v.trim());
  const d = toE164(v).slice(1);
  return /^\d{11,15}$/.test(d);
}

export function identifierValue(channel: Channel, v: string): string {
  return channel === "email" ? v.trim().toLowerCase() : toE164(v);
}

/** Mobile (+92 prefix) / e-mail input that switches keyboard type per channel. */
export function IdentifierInput({ channel, value, onChange }: { channel: Channel; value: string; onChange: (v: string) => void }) {
  if (channel === "email")
    return (
      <input
        className="input h-12"
        type="email"
        inputMode="email"
        autoComplete="email"
        autoCapitalize="off"
        placeholder="you@example.com"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoFocus
      />
    );
  return (
    <div className="flex h-12 overflow-hidden rounded-xl border border-black/10 bg-white focus-within:border-brand-500 focus-within:ring-4 focus-within:ring-brand-500/15 dark:border-white/10 dark:bg-white/5" dir="ltr">
      <span className="flex items-center gap-1.5 border-e border-black/10 px-3 text-sm font-semibold text-ink-soft dark:border-white/10 dark:text-slate-300">🇵🇰 +92</span>
      <input
        className="min-w-0 flex-1 bg-transparent px-3 text-base outline-none placeholder:text-ink-mute/70"
        type="tel"
        inputMode="tel"
        autoComplete="tel-national"
        placeholder="300 1234567"
        value={value}
        onChange={(e) => onChange(e.target.value.replace(/[^\d\s+-]/g, ""))}
        autoFocus
      />
    </div>
  );
}

export function useCountdown(): [number, (s: number) => void] {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft((x) => x - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);
  return [left, setLeft];
}
