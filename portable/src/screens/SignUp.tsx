/**
 * Passwordless sign-up: pick a role → name + mobile/e-mail → one-time code → session.
 *   POST /auth/signup      {name, mobile|email, role}      (no password)
 *   POST /auth/verify-otp  {identifier, code, purpose: "signup"}
 */
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Briefcase, Building, CheckCircle2, Home, KeyRound, LineChart, Mail, Smartphone, Store, UserRound } from "lucide-react";
import { toast } from "sonner";
import { ApiError, post } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SIGNUP_ROLES, useAuth, type Session, type SignupRole } from "@/store/auth";
import { usePrefs } from "@/store/prefs";
import { Button, Field, Input, OtpInput, Segmented } from "@/components/ui";
import { AuthLayout, channelWord, DevOtpHint, IdentifierInput, identifierValue, ResendButton, SmsConsentFields, useCountdown, useSmsCodeAutofill, validIdentifier, type Channel } from "./AuthLayout";

const ROLE_ICONS: Record<SignupRole, typeof Home> = {
  buyer: Home,
  seller: Store,
  investor: LineChart,
  agent: Briefcase,
  landlord: Building,
  tenant: KeyRound,
};

interface SignupResult {
  verification: {
    sent_to: string[];
    channels: string[];
    expires_in_seconds: number;
    /** Per identifier: "sent" (real provider) or "simulated" (server test mode). */
    delivery?: Record<string, "sent" | "simulated">;
    dev_otp?: Record<string, string> | null;
  };
}

type Step = "role" | "details" | "verify";
const STEPS: { key: Step; label: string }[] = [
  { key: "role", label: "I am a" },
  { key: "details", label: "Details" },
  { key: "verify", label: "Verify" },
];

export default function SignUp() {
  const [sp] = useSearchParams();
  const next = sp.get("next") || "/";
  const nav = useNavigate();
  const setSession = useAuth((s) => s.setSession);
  const setOnboarded = usePrefs((s) => s.setOnboarded);
  const [step, setStep] = useState<Step>("role");
  const [role, setRole] = useState<SignupRole>("buyer");
  const [name, setName] = useState("");
  const [channel, setChannel] = useState<Channel>((sp.get("via") as Channel) || "mobile");
  const [raw, setRaw] = useState(sp.get("id") ?? "");
  const [sent, setSent] = useState<SignupResult["verification"] | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [taken, setTaken] = useState(false);
  const [smsConsent, setSmsConsent] = useState(false);
  const [cooldown, setCooldown] = useCountdown();
  const [codeRequests, setCodeRequests] = useState(0);
  const identifier = identifierValue(channel, raw);
  const target = sent?.sent_to[0] ?? identifier;
  const stepIdx = STEPS.findIndex((s) => s.key === step);

  const submit = async () => {
    setBusy(true);
    setTaken(false);
    try {
      const r = await post<SignupResult>("/auth/signup", { name: name.trim(), role, [channel]: identifier, sms_consent: channel === "mobile" && smsConsent });
      setSent(r.verification);
      setStep("verify");
      setCooldown(30);
      setCodeRequests((n) => n + 1);
      const to = r.verification.sent_to;
      if (to.some((t) => r.verification.delivery?.[t] === "sent")) toast.success(`Verification code sent by ${to.map(channelWord).join(" & ")} to ${to.join(" & ")}`);
      else toast.info("Test mode: the server didn't send a real message — use the code shown below.");
    } catch (e) {
      if (e instanceof ApiError && (e.code === "email_taken" || e.code === "mobile_taken")) setTaken(true);
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const verify = async (c = code) => {
    if (c.length < 6) return;
    setBusy(true);
    try {
      const r = await post<Session>("/auth/verify-otp", { identifier: target, code: c, purpose: "signup" });
      setSession(r);
      setOnboarded(true);
      toast.success("Account verified — welcome to Arz-e-Pak!");
      nav(next !== "/" ? next : role === "seller" || role === "agent" || role === "landlord" ? "/listings" : "/", { replace: true });
    } catch (e) {
      toast.error((e as Error).message);
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    try {
      const r = await post<{ dev_otp?: string | null }>("/auth/resend-otp", { identifier: target, code: "", purpose: "signup", sms_consent: channel === "mobile" && smsConsent });
      if (r.dev_otp) setSent((x) => (x ? { ...x, dev_otp: { [target]: r.dev_otp! } } : x));
      setCooldown(30);
      setCodeRequests((n) => n + 1);
      toast.success("New code sent");
    } catch (e) {
      const retry = e instanceof ApiError ? (e.detail as { retry_after_seconds?: number })?.retry_after_seconds : undefined;
      if (retry) setCooldown(retry);
      toast.error((e as Error).message);
    }
  };

  // Android: fill the code from the SMS once the user allows it (only when a real SMS was sent).
  useSmsCodeAutofill(step === "verify" && channel === "mobile" && sent?.delivery?.[target] === "sent", (c) => {
    setCode(c);
    void verify(c);
  }, codeRequests);

  return (
    <AuthLayout
      title={step === "role" ? "Create your account" : step === "details" ? "Your details" : "Verify it’s you"}
      subtitle={
        step === "role"
          ? "Tell us how you’ll use Watan-e-Pak — we’ll tailor your home screen and AI assistant."
          : step === "details"
            ? "No password needed. We’ll send a one-time code by SMS or e-mail."
            : `Enter the 6-digit code we sent to ${sent?.sent_to.join(" and ")}.`
      }
    >
      <div className="mb-6 flex items-center gap-2 text-xs font-semibold">
        {STEPS.map((s, i) => (
          <div key={s.key} className="flex flex-1 items-center gap-2">
            <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full", i < stepIdx ? "bg-brand-600 text-white" : i === stepIdx ? "bg-gold-gradient text-brand-950" : "bg-black/5 text-ink-mute dark:bg-white/10")}>
              {i < stepIdx ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
            </span>
            <span className={cn("truncate", i <= stepIdx ? "text-ink dark:text-white" : "text-ink-mute")}>{s.label}</span>
            {i < STEPS.length - 1 && <span className="h-px flex-1 bg-black/10 dark:bg-white/10" />}
          </div>
        ))}
      </div>

      <AnimatePresence mode="wait">
        {step === "role" && (
          <motion.div key="role" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }}>
            <div className="grid grid-cols-2 gap-3">
              {SIGNUP_ROLES.map((r) => {
                const Icon = ROLE_ICONS[r.value];
                const on = role === r.value;
                return (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => setRole(r.value)}
                    className={cn(
                      "flex flex-col items-start gap-2 rounded-2xl border p-4 text-start transition active:scale-[.98]",
                      on ? "border-brand-600 bg-brand-50 ring-4 ring-brand-500/15 dark:bg-brand-500/15" : "border-black/10 bg-white dark:border-white/10 dark:bg-white/5",
                    )}
                  >
                    <span className={cn("flex h-10 w-10 items-center justify-center rounded-xl", on ? "bg-brand-700 text-white" : "bg-brand-50 text-brand-700 dark:bg-white/10 dark:text-brand-200")}>
                      <Icon className="h-5 w-5" />
                    </span>
                    <span>
                      <span className="block font-display font-bold text-brand-900 dark:text-white">{r.label}</span>
                      <span className="block text-xs text-ink-mute dark:text-slate-400">{r.hint}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            {/* Mirrors the server: agent / developer are requested at sign-up and granted by an admin. */}
            <p className={cn("mt-4 rounded-xl p-3 text-xs", role === "agent" ? "bg-gold-50 text-gold-900 dark:bg-gold-500/10 dark:text-gold-100" : "text-ink-mute dark:text-slate-400")}>
              {role === "agent"
                ? "Agent accounts are approved by an administrator. You’ll start as a regular member and get agent access once your request is approved."
                : "Agent and developer accounts are approved by an administrator."}
            </p>
            <Button size="lg" className="mt-6 w-full" onClick={() => setStep("details")}>
              Continue as {SIGNUP_ROLES.find((r) => r.value === role)?.label}
            </Button>
          </motion.div>
        )}

        {step === "details" && (
          <motion.form
            key="details"
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <Field label="Full name">
              <Input icon={<UserRound className="h-4 w-4" />} className="h-12" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ahmed Khan" autoComplete="name" required />
            </Field>
            <Segmented
              value={channel}
              onChange={(c) => {
                setChannel(c);
                setRaw("");
                setTaken(false);
              }}
              options={[
              { value: "mobile", label: "SMS", icon: <Smartphone className="h-4 w-4" /> },
                { value: "email", label: "E-mail", icon: <Mail className="h-4 w-4" /> },
              ]}
            />
            <Field label={channel === "mobile" ? "Mobile number" : "E-mail address"}>
              <IdentifierInput channel={channel} value={raw} onChange={(value) => { setRaw(value); setSmsConsent(false); }} />
            </Field>
            {channel === "mobile" && (
              <SmsConsentFields
                consent={smsConsent}
                onConsent={setSmsConsent}
                onPick={(number) => {
                  setRaw(number);
                  setSmsConsent(false);
                }}
              />
            )}
            {taken && (
              <div className="rounded-xl bg-gold-50 p-3 text-sm text-gold-900 dark:bg-gold-500/10 dark:text-gold-100">
                You already have an account.{" "}
                <Link to={`/signin?via=${channel}&id=${encodeURIComponent(raw)}`} className="link">
                  Sign in instead
                </Link>
              </div>
            )}
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={name.trim().length < 2 || !validIdentifier(channel, raw) || (channel === "mobile" && !smsConsent)}>
              Send verification code
            </Button>
            <button type="button" className="w-full text-sm font-semibold text-ink-mute" onClick={() => setStep("role")}>
              ← Change role
            </button>
            <p className="text-center text-xs text-ink-mute dark:text-slate-400">By continuing you agree to the Watan-e-Pak Terms and Privacy policy.</p>
          </motion.form>
        )}

        {step === "verify" && (
          <motion.form
            key="verify"
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault();
              void verify();
            }}
          >
            <OtpInput value={code} onChange={setCode} onComplete={(c) => void verify(c)} />
            <DevOtpHint
              code={sent?.dev_otp?.[target] ?? Object.values(sent?.dev_otp ?? {})[0]}
              onUse={(c) => {
                setCode(c);
                void verify(c);
              }}
            />
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={code.length < 6}>
              Verify & create account
            </Button>
            <div className="flex items-center justify-between">
              <button type="button" className="text-sm font-semibold text-ink-mute" onClick={() => setStep("details")}>
                ← Edit details
              </button>
              <ResendButton seconds={cooldown} onResend={() => void resend()} />
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      <p className="mt-10 text-center text-sm text-ink-mute dark:text-slate-400">
        Already have an account?{" "}
        <Link to={`/signin${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} className="link">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
