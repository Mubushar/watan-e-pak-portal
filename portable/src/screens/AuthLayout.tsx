import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, Bot, LineChart, MapPinned, Phone, ShieldCheck, Smartphone } from "lucide-react";
import { HERO } from "@/lib/images";
import { isAndroidApp, pickDeviceNumber, waitForSmsCode } from "@/lib/phoneNumberHint";
import { Logo } from "@/components/ui";

const PERKS: [typeof Bot, string][] = [
  [Bot, "Voice & chat AI assistant for buying, selling and investing"],
  [MapPinned, "Verified listings across Pakistan's top cities and societies"],
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

/** The phone OTP route uses SMS; email identifiers use e-mail. */
export function channelWord(target: string): string {
  return target.includes("@") ? "e-mail" : "SMS";
}

/**
 * Shown when the server has no SMS / e-mail provider for this channel (test mode):
 * the backend returns the code instead of delivering it — see backend/delivery.py.
 */
export function DevOtpHint({ code, onUse }: { code?: string | null; onUse: (c: string) => void }) {
  if (!code) return null;
  return (
    <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-dashed border-gold-300 bg-gold-50 px-3 py-2.5 text-xs text-gold-800 dark:border-gold-500/30 dark:bg-gold-500/10 dark:text-gold-200">
      <span>
        <b className="block">Test mode — nothing was sent</b>
        The server has no SMS/e-mail provider set up yet, so here is your code: <b className="font-mono text-sm">{code}</b>
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

/**
 * The full international number: "+92 300 1234567" / "0092…" → "+923001234567", "+971 50…" kept.
 * A local Pakistani "0300 1234567" is still accepted and gets +92.
 */
export function toE164(raw: string): string {
  let d = raw.replace(/[^\d+]/g, "").replace(/(?!^)\+/g, "");
  if (d.startsWith("+")) return d;
  if (d.startsWith("00")) return `+${d.slice(2)}`;
  if (d.startsWith("92") && d.length >= 12) return `+${d}`;
  if (d.startsWith("0")) d = d.slice(1);
  return `+92${d}`;
}

/** "+923001234567" → "+92 300 1234567" (other countries: as typed). */
export function formatPhone(e164: string): string {
  const m = e164.match(/^\+92(\d{3})(\d{7})$/);
  return m ? `+92 ${m[1]} ${m[2]}` : e164;
}

export function validIdentifier(channel: Channel, v: string): boolean {
  if (channel === "email") return /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(v.trim());
  const e164 = toE164(v);
  // Pakistan: a 10-digit mobile number (3xx xxxxxxx); elsewhere 8–15 digits like the server.
  return e164.startsWith("+92") ? /^\+923\d{9}$/.test(e164) : /^\+[1-9]\d{7,14}$/.test(e164);
}

export function identifierValue(channel: Channel, v: string): string {
  return channel === "email" ? v.trim().toLowerCase() : toE164(v);
}

/** Mobile (full number with country code) / e-mail input that switches keyboard type per channel. */
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
    <div dir="ltr">
      <div className="flex h-12 overflow-hidden rounded-xl border border-black/10 bg-white focus-within:border-brand-500 focus-within:ring-4 focus-within:ring-brand-500/15 dark:border-white/10 dark:bg-white/5">
        <span className="flex items-center border-e border-black/10 px-3 text-ink-mute dark:border-white/10">
          <Phone className="h-4 w-4" />
        </span>
        <input
          className="min-w-0 flex-1 bg-transparent px-3 text-base outline-none placeholder:text-ink-mute/70"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="+92 300 1234567"
          value={value}
          onFocus={() => !value && onChange("+92 ")}
          onChange={(e) => onChange(e.target.value.replace(/[^\d\s+-]/g, ""))}
          autoFocus
        />
      </div>
      <p className="mt-1.5 text-xs text-ink-mute dark:text-slate-400">Full number with country code, e.g. +92 300 1234567 or +971 50 123 4567.</p>
    </div>
  );
}

/**
 * Below the mobile field: "use this phone's number" (Android SIM picker) and the SMS consent
 * the API requires before it sends a phone code. Changing the number clears the consent.
 */
export function SmsConsentFields({ consent, onConsent, onPick }: { consent: boolean; onConsent: (v: boolean) => void; onPick: (formatted: string) => void }) {
  return (
    <div className="space-y-3">
      {isAndroidApp && (
        <button
          type="button"
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-brand-600/30 py-2.5 text-sm font-semibold text-brand-700 dark:text-brand-300"
          onClick={() => void pickDeviceNumber().then((n) => n && onPick(formatPhone(toE164(n))))}
        >
          <Smartphone className="h-4 w-4" /> Use a number from this phone
        </button>
      )}
      <label className="flex items-start gap-2.5 rounded-xl bg-black/[.03] p-3 text-xs leading-5 text-ink-soft dark:bg-white/5 dark:text-slate-300">
        <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-brand-700" checked={consent} onChange={(e) => onConsent(e.target.checked)} />
        <span>
          I agree to receive a one-time verification code by SMS at this number. Standard SMS rates may apply.
          {isAndroidApp && " Android will ask before the app reads the code message."}
        </span>
      </label>
    </div>
  );
}

/** While the code screen is open on Android, fill the code from the SMS once the user allows it. */
export function useSmsCodeAutofill(active: boolean, onCode: (code: string) => void, requestKey: unknown) {
  const latest = useRef(onCode);
  latest.current = onCode;
  useEffect(() => (active ? waitForSmsCode((code) => latest.current(code)) : undefined), [active, requestKey]);
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
