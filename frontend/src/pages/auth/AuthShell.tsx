import { useRef, type ReactNode } from "react";
import { motion } from "framer-motion";
import { Bot, LineChart, MapPinned, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { HERO } from "@/lib/images";
import { Logo } from "@/components/layout/Chrome";

/** Split-screen frame shared by sign-in, sign-up and password reset. */
export function AuthShell({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <div className="container grid min-h-[calc(100vh-120px)] items-center gap-10 py-10 lg:grid-cols-2">
      <div className="relative hidden h-full min-h-[600px] overflow-hidden rounded-[2rem] bg-brand-950 p-10 text-white lg:flex lg:flex-col">
        <img src={HERO.panorama} alt="" className="absolute inset-0 h-full w-full object-cover opacity-50" />
        <div className="absolute inset-0 bg-gradient-to-t from-brand-950 via-brand-950/70 to-brand-950/20" />
        <div className="relative">
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
            {[
              [Bot, "24 AI agents for buying, selling, leasing and investing"],
              [MapPinned, "GIS scores, nearby places and master plans for every listing"],
              [LineChart, "Live market trends, forecasts and news impact"],
              [ShieldCheck, "OTP-verified accounts and role-based access"],
            ].map(([I, t], i) => {
              const Icon = I as typeof Bot;
              return (
                <li key={i} className="flex items-center gap-3">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
                    <Icon className="h-4 w-4 text-gold-300" />
                  </span>
                  {t as string}
                </li>
              );
            })}
          </ul>
        </div>
      </div>
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mx-auto w-full max-w-md">
        <h1 className="font-display text-3xl font-bold text-brand-900 dark:text-white">{title}</h1>
        {subtitle && <p className="mt-2 text-ink-mute">{subtitle}</p>}
        <div className="mt-8">{children}</div>
      </motion.div>
    </div>
  );
}

/** Six-box one-time-code input with paste support. */
export function OtpInput({ value, onChange, length = 6 }: { value: string; onChange: (v: string) => void; length?: number }) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length }, (_, i) => value[i] ?? "");
  const setAt = (i: number, ch: string) => {
    const next = digits.slice();
    next[i] = ch;
    onChange(next.join("").slice(0, length));
  };
  return (
    <div className="flex justify-between gap-2" dir="ltr">
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => (refs.current[i] = el)}
          value={d}
          inputMode="numeric"
          maxLength={1}
          aria-label={`Digit ${i + 1}`}
          className="input h-14 w-12 text-center font-display text-xl font-bold"
          onChange={(e) => {
            const ch = e.target.value.replace(/\D/g, "").slice(-1);
            setAt(i, ch);
            if (ch && i < length - 1) refs.current[i + 1]?.focus();
          }}
          onKeyDown={(e) => {
            if (e.key === "Backspace" && !d && i > 0) refs.current[i - 1]?.focus();
          }}
          onPaste={(e) => {
            const text = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, length);
            if (text) {
              e.preventDefault();
              onChange(text);
              refs.current[Math.min(text.length, length) - 1]?.focus();
            }
          }}
        />
      ))}
    </div>
  );
}

/** Development helper: the backend exposes OTPs when PORTAL_AUTH_EXPOSE_OTP is on. */
/** What the backend says about an issued code (`/auth/otp/request`, `/auth/password/reset-request`, …). */
export interface OtpHint {
  sent_to?: string;
  channel?: string;
  /** "sent" = delivered by a real SMS / e-mail provider; "simulated" = no provider configured. */
  delivery?: "sent" | "simulated";
  /** Only returned for simulated channels (or when PORTAL_AUTH_EXPOSE_OTP is on). */
  dev_otp?: string | null;
}

export const channelWord = (to: string) => (to.includes("@") ? "e-mail" : "SMS");

/** Toast for a freshly issued code: real delivery, or the server's test mode. */
export function announceCode(r: OtpHint, fallbackTo?: string) {
  const to = r.sent_to ?? fallbackTo;
  if (r.delivery === "simulated" || (r.dev_otp && r.delivery !== "sent"))
    toast.info("Test mode: the server didn’t send a real message — use the code shown below.");
  else toast.success(to ? `Code sent by ${channelWord(to)} to ${to}` : "Code sent");
}

export function DevOtpHint({ code, onUse }: { code?: string | null; onUse: (c: string) => void }) {
  if (!code) return null;
  return (
    <div className="mt-3 flex items-center justify-between gap-2 rounded-xl border border-dashed border-gold-300 bg-gold-50 px-3 py-2 text-xs text-gold-800 dark:border-gold-500/30 dark:bg-gold-500/10 dark:text-gold-200">
      <span>
        Test mode — your code is <b className="font-mono text-sm">{code}</b>
      </span>
      <button type="button" className="font-semibold underline" onClick={() => onUse(code)}>
        Use it
      </button>
    </div>
  );
}
