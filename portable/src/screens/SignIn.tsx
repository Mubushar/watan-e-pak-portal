/**
 * Passwordless sign-in: mobile number or e-mail → one-time code → session.
 *   POST /auth/otp/request {identifier}
 *   POST /auth/otp/verify  {identifier, code}
 */
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Mail, Smartphone } from "lucide-react";
import { toast } from "sonner";
import { ApiError, post } from "@/lib/api";
import { useAuth, type Session } from "@/store/auth";
import { usePrefs } from "@/store/prefs";
import { Button, Field, OtpInput, Segmented } from "@/components/ui";
import { AuthLayout, channelWord, DevOtpHint, IdentifierInput, identifierValue, ResendButton, SmsConsentFields, useCountdown, useSmsCodeAutofill, validIdentifier, type Channel } from "./AuthLayout";

interface OtpSent {
  sent_to?: string;
  channel?: string;
  dev_otp?: string | null;
  /** "sent" = delivered by a real provider; "simulated" = server test mode. */
  delivery?: "sent" | "simulated";
  expires_in_seconds?: number;
  /** Set when the server can't say whether the account exists ("If that account exists, …"). */
  note?: string;
}

export default function SignIn() {
  const [sp] = useSearchParams();
  const next = sp.get("next") || "/";
  const nav = useNavigate();
  const setSession = useAuth((s) => s.setSession);
  const setOnboarded = usePrefs((s) => s.setOnboarded);
  const [channel, setChannel] = useState<Channel>((sp.get("via") as Channel) || "mobile");
  const [raw, setRaw] = useState(sp.get("id") ?? "");
  const [sent, setSent] = useState<OtpSent | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [smsConsent, setSmsConsent] = useState(false);
  const [cooldown, setCooldown] = useCountdown();
  const [codeRequests, setCodeRequests] = useState(0);
  const identifier = identifierValue(channel, raw);

  const request = async () => {
    setBusy(true);
    setNotFound(false);
    try {
      const r = await post<OtpSent>("/auth/otp/request", { identifier, sms_consent: channel === "mobile" && smsConsent });
      setSent(r);
      setCode("");
      setCooldown(30);
      setCodeRequests((n) => n + 1);
      if (r.dev_otp && r.delivery !== "sent") toast.info("Test mode: the server didn't send a real message — use the code shown below.");
      else if (!r.delivery) toast.info(`If ${r.sent_to ?? identifier} has a Watan-e-Pak account, a code is on its way. No account yet? Create one below.`);
      else toast.success(`Code sent by ${channelWord(r.sent_to ?? identifier)} to ${r.sent_to ?? identifier}`);
    } catch (e) {
      const retry = e instanceof ApiError ? (e.detail as { retry_after_seconds?: number })?.retry_after_seconds : undefined;
      if (retry) {
        setCooldown(retry);
        setSent((s) => s ?? { sent_to: identifier });
      }
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const verify = async (c = code) => {
    if (c.length < 6) return;
    setBusy(true);
    try {
      const r = await post<Session>("/auth/otp/verify", { identifier, code: c, purpose: "login" });
      setSession(r);
      setOnboarded(true);
      toast.success(`Welcome back${r.user.name ? `, ${r.user.name.split(" ")[0]}` : ""}!`);
      nav(next, { replace: true });
    } catch (e) {
      // The backend answers "sent" for unknown accounts (no user enumeration),
      // so a missing code here usually means there is no account yet.
      if (e instanceof ApiError && e.code === "no_otp") setNotFound(true);
      toast.error((e as Error).message);
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  // Android: fill the code from the SMS once the user allows it (only when a real SMS was sent).
  useSmsCodeAutofill(!!sent && channel === "mobile" && sent.delivery === "sent", (c) => {
    setCode(c);
    void verify(c);
  }, codeRequests);

  return (
    <AuthLayout
      title={sent ? "Enter your code" : "Welcome back"}
      subtitle={sent ? sent.delivery
        ? `We sent a 6-digit code by ${channelWord(sent.sent_to ?? identifier)} to ${sent.sent_to ?? identifier}. It expires in ${Math.round((sent.expires_in_seconds ?? 300) / 60)} minutes.`
        : `If ${sent.sent_to ?? identifier} has a Watan-e-Pak account, we've sent it a 6-digit code. No code? Create an account below.` :"Sign in with a one-time code sent by SMS to your mobile or by e-mail."}
    >
      <AnimatePresence mode="wait">
        {!sent ? (
          <motion.form
            key="id"
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault();
              void request();
            }}
          >
            <Segmented
              value={channel}
              onChange={(c) => {
                setChannel(c);
                setRaw("");
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
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!validIdentifier(channel, raw) || (channel === "mobile" && !smsConsent)}>
              Send me a code
            </Button>
          </motion.form>
        ) : (
          <motion.form
            key="otp"
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
            <DevOtpHint code={sent.dev_otp} onUse={(c) => { setCode(c); void verify(c); }} />
            {notFound && (
              <div className="rounded-xl bg-gold-50 p-3 text-sm text-gold-900 dark:bg-gold-500/10 dark:text-gold-100">
                No account found for <b>{identifier}</b>.{" "}
                <Link to={`/signup?via=${channel}&id=${encodeURIComponent(raw)}`} className="link">
                  Create one now
                </Link>
              </div>
            )}
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={code.length < 6}>
              Verify & sign in
            </Button>
            <div className="flex items-center justify-between">
              <button type="button" className="text-sm font-semibold text-ink-mute" onClick={() => setSent(null)}>
                ← Change {channel === "mobile" ? "number" : "e-mail"}
              </button>
              <ResendButton seconds={cooldown} onResend={() => void request()} />
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      <p className="mt-10 text-center text-sm text-ink-mute dark:text-slate-400">
        New to Watan-e-Pak?{" "}
        <Link to={`/signup${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} className="link">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}
