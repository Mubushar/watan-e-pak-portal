import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Briefcase, Building, CheckCircle2, Home, KeyRound, LineChart, Mail, Phone, Store, UserRound } from "lucide-react";
import { toast } from "sonner";
import { post } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuth, type Session } from "@/store/auth";
import { Button, Field, Input } from "@/components/ui";
import { AuthShell, DevOtpHint, OtpInput } from "./AuthShell";

const ROLES = [
  { value: "buyer", label: "Buyer", icon: Home },
  { value: "seller", label: "Seller", icon: Store },
  { value: "tenant", label: "Tenant", icon: KeyRound },
  { value: "landlord", label: "Landlord", icon: Building },
  { value: "investor", label: "Investor", icon: LineChart },
  { value: "agent", label: "Agent", icon: Briefcase },
  { value: "developer", label: "Developer", icon: Building },
  { value: "user", label: "Just browsing", icon: UserRound },
];

interface SignupResult {
  verification: { sent_to: string[]; channels: string[]; dev_otp?: Record<string, string> | null };
}

function strength(pw: string) {
  let s = 0;
  if (pw.length >= 8) s++;
  if (/[A-Z]/.test(pw)) s++;
  if (/[0-9]/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return s;
}

export default function Signup() {
  const nav = useNavigate();
  const setSession = useAuth((s) => s.setSession);
  const [form, setForm] = useState({ name: "", email: "", mobile: "", password: "", role: "buyer" });
  const [step, setStep] = useState<"details" | "verify">("details");
  const [sent, setSent] = useState<SignupResult["verification"] | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const identifier = sent?.sent_to[0] ?? form.email ?? form.mobile;
  const s = strength(form.password);

  const submit = async () => {
    setBusy(true);
    try {
      const r = await post<SignupResult>("/auth/signup", {
        name: form.name,
        email: form.email || undefined,
        mobile: form.mobile || undefined,
        password: form.password,
        role: form.role,
      });
      setSent(r.verification);
      setStep("verify");
      toast.success(`Verification code sent to ${r.verification.sent_to.join(" & ")}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    try {
      const r = await post<Session>("/auth/verify-otp", { identifier, code, purpose: "signup" });
      if (r.token) {
        setSession(r);
        toast.success("Account verified — welcome to Arz-e-Pak!");
        nav("/app", { replace: true });
      } else {
        toast.success("Verified — please sign in");
        nav("/login");
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title={step === "details" ? "Create your account" : "Verify it’s you"} subtitle={step === "details" ? "Free for buyers, tenants and investors. Agencies can upgrade any time." : `We sent a 6-digit code to ${sent?.sent_to.join(" and ")}.`}>
      <div className="mb-6 flex items-center gap-3 text-xs font-semibold">
        {["Details", "Verify"].map((l, i) => {
          const active = (i === 0 && step === "details") || (i === 1 && step === "verify");
          const done = i === 0 && step === "verify";
          return (
            <div key={l} className="flex flex-1 items-center gap-2">
              <span className={cn("flex h-7 w-7 items-center justify-center rounded-full", done ? "bg-brand-600 text-white" : active ? "bg-gold-gradient text-brand-950" : "bg-black/5 text-ink-mute dark:bg-white/10")}>
                {done ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
              </span>
              <span className={active || done ? "text-ink dark:text-white" : "text-ink-mute"}>{l}</span>
              {i === 0 && <span className="h-px flex-1 bg-black/10 dark:bg-white/10" />}
            </div>
          );
        })}
      </div>
      <AnimatePresence mode="wait">
        {step === "details" ? (
          <motion.form
            key="d"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <div>
              <p className="label">I am a…</p>
              <div className="grid grid-cols-4 gap-2">
                {ROLES.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    onClick={() => setForm({ ...form, role: r.value })}
                    className={cn("flex flex-col items-center gap-1 rounded-xl border px-2 py-2.5 text-[11px] font-semibold transition", form.role === r.value ? "border-brand-600 bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-white" : "border-black/10 hover:border-brand-300 dark:border-white/10")}
                  >
                    <r.icon className="h-4 w-4" />
                    {r.label}
                  </button>
                ))}
              </div>
            </div>
            <Field label="Full name">
              <Input icon={<UserRound className="h-4 w-4" />} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ahmed Khan" required />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="E-mail">
                <Input icon={<Mail className="h-4 w-4" />} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" />
              </Field>
              <Field label="Mobile">
                <Input icon={<Phone className="h-4 w-4" />} value={form.mobile} onChange={(e) => setForm({ ...form, mobile: e.target.value })} placeholder="03xx xxxxxxx" />
              </Field>
            </div>
            <Field label="Password" hint="At least 8 characters with a number and a capital letter.">
              <Input icon={<KeyRound className="h-4 w-4" />} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="••••••••" autoComplete="new-password" required />
              <div className="mt-2 flex gap-1">
                {[0, 1, 2, 3].map((i) => (
                  <span key={i} className={cn("h-1.5 flex-1 rounded-full", i < s ? (s >= 3 ? "bg-brand-500" : s === 2 ? "bg-gold-400" : "bg-red-400") : "bg-black/10 dark:bg-white/10")} />
                ))}
              </div>
            </Field>
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!form.name || (!form.email && !form.mobile) || form.password.length < 8}>
              Continue
            </Button>
            <p className="text-center text-xs text-ink-mute">
              By continuing you agree to our{" "}
              <Link to="/pages/terms" className="link">
                Terms
              </Link>{" "}
              and{" "}
              <Link to="/pages/privacy" className="link">
                Privacy policy
              </Link>
              .
            </p>
          </motion.form>
        ) : (
          <motion.form
            key="v"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void verify();
            }}
          >
            <OtpInput value={code} onChange={setCode} />
            <DevOtpHint code={sent?.dev_otp?.[identifier] ?? Object.values(sent?.dev_otp ?? {})[0]} onUse={setCode} />
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={code.length < 6}>
              Verify & create account
            </Button>
            <div className="flex justify-between text-xs">
              <button type="button" className="font-semibold text-ink-mute hover:text-ink" onClick={() => setStep("details")}>
                ← Edit details
              </button>
              <button
                type="button"
                className="font-semibold text-brand-700 hover:underline dark:text-brand-300"
                onClick={() =>
                  post<{ dev_otp?: string }>("/auth/resend-otp", { identifier, code: "", purpose: "signup" })
                    .then((r) => {
                      if (r.dev_otp) setSent((x) => (x ? { ...x, dev_otp: { [identifier]: r.dev_otp! } } : x));
                      toast.success("New code sent");
                    })
                    .catch((e: Error) => toast.error(e.message))
                }
              >
                Resend code
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>
      <p className="mt-8 text-center text-sm text-ink-mute">
        Already have an account?{" "}
        <Link to="/login" className="link">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}
