import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { KeyRound, Lock, Mail, Smartphone, UserRound } from "lucide-react";
import { toast } from "sonner";
import { ApiError, post } from "@/lib/api";
import { demoAccountsFrom, useAuth, type Session } from "@/store/auth";
import { useApi } from "@/hooks/useApi";
import { Button, Field, Input, Segmented } from "@/components/ui";
import { announceCode, AuthShell, DevOtpHint, OtpInput, type OtpHint } from "./AuthShell";

type Mode = "password" | "otp";

export default function Login() {
  const [sp] = useSearchParams();
  const next = sp.get("next") || "/app";
  const nav = useNavigate();
  const setSession = useAuth((s) => s.setSession);
  const [mode, setMode] = useState<Mode>("password");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [otpSent, setOtpSent] = useState<{ purpose: "login" | "signup"; dev?: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  // Demo accounts are listed only where the server seeds them (never in production).
  const cfg = useApi<{ demo_accounts?: unknown }>("/auth/config", undefined, { staleTime: 5 * 60_000 });
  const demoAccounts = demoAccountsFrom(cfg.data);

  const finish = (s: Session) => {
    setSession(s);
    toast.success(`Welcome back, ${s.user.name ?? s.user.email}`);
    nav(next, { replace: true });
  };

  const loginPassword = async (id = identifier, pw = password) => {
    setBusy(true);
    try {
      finish(await post<Session>("/auth/login", { identifier: id, password: pw }));
    } catch (e) {
      const d = e instanceof ApiError ? (e.detail as (OtpHint & { otp_required?: boolean }) | undefined) : undefined;
      if (d?.otp_required) {
        setOtpSent({ purpose: "signup", dev: d.dev_otp });
        setMode("otp");
        toast.info(
          d.delivery === "simulated" ? "Your account isn’t verified yet — use the test code shown below." : "Your account isn’t verified yet — enter the code we just sent.",
        );
      } else toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const requestOtp = async () => {
    setBusy(true);
    try {
      const r = await post<OtpHint>("/auth/otp/request", { identifier });
      setOtpSent({ purpose: "login", dev: r.dev_otp });
      announceCode(r);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const verifyOtp = async () => {
    setBusy(true);
    try {
      const path = otpSent?.purpose === "signup" ? "/auth/verify-otp" : "/auth/otp/verify";
      const r = await post<Session & { token?: string }>(path, { identifier, code, purpose: otpSent?.purpose ?? "login" });
      if (r.token) finish(r);
      else if (otpSent?.purpose === "signup") {
        toast.success("Account verified — signing you in");
        await loginPassword();
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your dashboard, saved searches and AI agents.">
      <Segmented
        value={mode}
        onChange={(m) => {
          setMode(m);
          setOtpSent(null);
          setCode("");
        }}
        className="w-full [&>button]:flex-1 [&>button]:justify-center"
        options={[
          { value: "password", label: "Password", icon: <Lock className="h-4 w-4" /> },
          { value: "otp", label: "One-time code", icon: <Smartphone className="h-4 w-4" /> },
        ]}
      />
      <form
        className="mt-6 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (mode === "password") void loginPassword();
          else if (!otpSent) void requestOtp();
          else void verifyOtp();
        }}
      >
        <Field label="E-mail or mobile">
          <Input icon={<Mail className="h-4 w-4" />} value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="E-mail, mobile (03xx xxxxxxx) or username" autoComplete="username" required />
        </Field>
        {mode === "password" ? (
          <Field label={<span className="flex justify-between">Password <Link to="/forgot" className="normal-case tracking-normal text-brand-700 dark:text-brand-300">Forgot?</Link></span>}>
            <Input icon={<KeyRound className="h-4 w-4" />} type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" required />
          </Field>
        ) : (
          otpSent && (
            <div>
              <p className="label">Enter the 6-digit code</p>
              <OtpInput value={code} onChange={setCode} />
              <DevOtpHint code={otpSent.dev} onUse={setCode} />
              <button type="button" onClick={requestOtp} className="mt-3 text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300">
                Resend code
              </button>
            </div>
          )
        )}
        <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!identifier || (mode === "password" ? !password : !!otpSent && code.length < 6)}>
          {mode === "password" ? "Sign in" : otpSent ? "Verify & sign in" : "Send me a code"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-ink-mute">
        New to Arz-e-Pak?{" "}
        <Link to="/signup" className="link">
          Create an account
        </Link>
      </p>

      {demoAccounts.length > 0 && (
      <div className="mt-8 rounded-2xl border border-black/5 bg-white p-4 dark:border-white/10 dark:bg-white/5">
        <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-ink-mute">
          <UserRound className="h-3.5 w-3.5" /> Demo accounts (seeded)
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {demoAccounts.map((a) => (
            <button
              key={a.email}
              type="button"
              disabled={busy}
              onClick={() => {
                setMode("password");
                setIdentifier(a.email);
                setPassword(a.password ?? "");
                if (a.password) void loginPassword(a.email, a.password);
              }}
              className="rounded-xl border border-black/5 px-3 py-2 text-start transition hover:border-brand-300 hover:bg-brand-50 dark:border-white/10 dark:hover:bg-white/5"
            >
              <span className="block text-sm font-semibold">{a.label ?? (a.role ? a.role.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : a.name ?? a.email)}</span>
              <span className="block truncate text-[11px] text-ink-mute">{a.email}</span>
            </button>
          ))}
        </div>
      </div>
      )}
    </AuthShell>
  );
}
