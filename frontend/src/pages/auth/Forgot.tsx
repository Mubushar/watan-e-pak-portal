import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { KeyRound, Mail } from "lucide-react";
import { toast } from "sonner";
import { post } from "@/lib/api";
import { Button, Field, Input } from "@/components/ui";
import { announceCode, AuthShell, DevOtpHint, OtpInput, type OtpHint } from "./AuthShell";

export default function Forgot() {
  const nav = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [smsConsent, setSmsConsent] = useState(false);
  const [sent, setSent] = useState<{ dev?: string | null } | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);

  const request = async () => {
    setBusy(true);
    try {
      const r = await post<OtpHint & { note?: string }>("/auth/password/reset-request", { identifier, sms_consent: identifier.includes("@") ? false : smsConsent });
      setSent({ dev: r.dev_otp });
      if (r.note) toast.success(r.note);
      else announceCode(r);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    setBusy(true);
    try {
      await post("/auth/password/reset", { identifier, code, new_password: pw });
      toast.success("Password updated — sign in with your new password");
      nav("/login");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Reset your password" subtitle={sent ? "Enter the code we sent and choose a new password." : "We’ll send a one-time code to your e-mail or mobile."}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void (sent ? reset() : request());
        }}
      >
        <Field label="E-mail or mobile">
          <Input icon={<Mail className="h-4 w-4" />} value={identifier} onChange={(e) => { setIdentifier(e.target.value); setSmsConsent(false); }} disabled={!!sent} required />
        </Field>
        {!sent && identifier && !identifier.includes("@") && <label className="flex items-start gap-2 text-xs leading-5 text-ink-mute"><input type="checkbox" className="mt-1" checked={smsConsent} onChange={(e) => setSmsConsent(e.target.checked)} />I agree to receive an SMS password reset code at this number. Message and data rates may apply.</label>}
        {sent && (
          <>
            <div>
              <p className="label">Reset code</p>
              <OtpInput value={code} onChange={setCode} />
              <DevOtpHint code={sent.dev} onUse={setCode} />
            </div>
            <Field label="New password">
              <Input icon={<KeyRound className="h-4 w-4" />} type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required />
            </Field>
          </>
        )}
        <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!identifier || (!sent && !identifier.includes("@") && !smsConsent) || (!!sent && (code.length < 6 || pw.length < 8))}>
          {sent ? "Update password" : "Send reset code"}
        </Button>
      </form>
      <p className="mt-8 text-center text-sm text-ink-mute">
        Remembered it?{" "}
        <Link to="/login" className="link">
          Back to sign in
        </Link>
      </p>
    </AuthShell>
  );
}
