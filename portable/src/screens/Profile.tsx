import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BadgeCheck, Building2, ChevronRight, Heart, LogIn, LogOut, Mail, Monitor, Moon, Phone, Server, Sun, UserPlus, LocateFixed } from "lucide-react";
import { toast } from "sonner";
import { apiBase, post } from "@/lib/api";
import { DEFAULT_API_BASE, normalizeServerUrl } from "@/lib/config";
import { runtime, runtimeLabel } from "@/lib/platform";
import { useChat } from "@/lib/assistant";
import { resetServerVoice, serverVoice, type ServerVoice } from "@/lib/voice";
import { roleLabel, useAuth } from "@/store/auth";
import { usePrefs, type ReplyLang, type Theme } from "@/store/prefs";
import { Avatar, Badge, Button, Field, Input, Segmented, TopBar } from "@/components/ui";
import { AdvertiseWithUs } from "@/components/Ads";

export default function Profile() {
  const nav = useNavigate();
  const { user, token, logout } = useAuth();
  const { theme, setTheme, voiceLang, setVoiceLang, replyLang, setReplyLang, serverUrl, setServerUrl } = usePrefs();
  const [voice, setVoice] = useState<ServerVoice | null>(null);
  useEffect(() => {
    void serverVoice().then(setVoice);
  }, [serverUrl]);
  const [server, setServer] = useState(serverUrl ?? "");
  const [testing, setTesting] = useState(false);

  const signOut = async () => {
    if (token) await post("/auth/logout").catch(() => undefined);
    logout();
    useChat.getState().clear();
    toast.success("Signed out");
    nav("/");
  };

  const testServer = async () => {
    const url = normalizeServerUrl(server) || DEFAULT_API_BASE;
    setTesting(true);
    try {
      const r = await fetch(`${url}/health`, { signal: AbortSignal.timeout(8000) });
      const j = (await r.json()) as { status?: string; version?: string };
      if (j.status !== "ok") throw new Error("Unexpected response");
      setServerUrl(normalizeServerUrl(server) || null);
      resetServerVoice();
      toast.success(`Connected to Watan-e-Pak server v${j.version ?? "?"}`);
    } catch {
      toast.error(`Can't reach ${url}. Check the address and that the backend is running.`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div>
      <TopBar title="Profile" />
      <div className="screen space-y-5 pt-4">
        {user ? (
          <div className="card overflow-hidden">
            <div className="flex items-center gap-4 bg-brand-gradient p-5 text-white">
              <Avatar name={user.name ?? user.email ?? user.mobile} className="h-14 w-14 text-lg" />
              <div className="min-w-0">
                <p className="truncate font-display text-xl font-bold">{user.name ?? "Watan-e-Pak member"}</p>
                <span className="chip mt-1 bg-white/15 text-gold-200">{roleLabel(user.role)}</span>
              </div>
            </div>
            <div className="divide-y divide-black/5 dark:divide-white/5">
              {user.mobile && (
                <div className="flex items-center gap-3 px-5 py-3 text-sm">
                  <Phone className="h-4 w-4 text-brand-600" /> <span className="flex-1">{user.mobile}</span>
                  {user.mobile_verified !== false && (
                    <Badge icon={<BadgeCheck className="h-3 w-3" />}>Verified</Badge>
                  )}
                </div>
              )}
              {user.email && (
                <div className="flex items-center gap-3 px-5 py-3 text-sm">
                  <Mail className="h-4 w-4 text-brand-600" /> <span className="flex-1 truncate">{user.email}</span>
                  {user.email_verified !== false && (
                    <Badge icon={<BadgeCheck className="h-3 w-3" />}>Verified</Badge>
                  )}
                </div>
              )}
              <Link to="/listings" className="flex items-center gap-3 px-5 py-3 text-sm font-semibold">
                <Building2 className="h-4 w-4 text-brand-600" /> <span className="flex-1">My listings</span> <ChevronRight className="h-4 w-4 text-ink-mute rtl:rotate-180" />
              </Link>
              <Link to="/survey" className="flex items-center gap-3 px-5 py-3 text-sm font-semibold">
                <LocateFixed className="h-4 w-4 text-brand-600" /> <span className="flex-1">Field survey (GPS + camera)</span> <ChevronRight className="h-4 w-4 text-ink-mute rtl:rotate-180" />
              </Link>
              <Link to="/saved" className="flex items-center gap-3 px-5 py-3 text-sm font-semibold">
                <Heart className="h-4 w-4 text-brand-600" /> <span className="flex-1">Saved properties</span> <ChevronRight className="h-4 w-4 text-ink-mute rtl:rotate-180" />
              </Link>
            </div>
          </div>
        ) : (
          <div className="card p-5 text-center">
            <p className="font-display text-lg font-bold">You're browsing as a guest</p>
            <p className="mt-1 text-sm text-ink-mute">Create a free account to list properties, save searches and get personal AI help.</p>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <Link to="/signup" className="btn btn-gold">
                <UserPlus className="h-4 w-4" /> Sign up
              </Link>
              <Link to="/signin" className="btn btn-outline">
                <LogIn className="h-4 w-4" /> Sign in
              </Link>
            </div>
          </div>
        )}

        <section className="card p-5">
          <p className="label">Appearance</p>
          <Segmented<Theme>
            value={theme}
            onChange={setTheme}
            options={[
              { value: "system", label: "Auto", icon: <Monitor className="h-4 w-4" /> },
              { value: "light", label: "Light", icon: <Sun className="h-4 w-4" /> },
              { value: "dark", label: "Dark", icon: <Moon className="h-4 w-4" /> },
            ]}
          />
        </section>

        <section className="card px-5 pt-5">
          <p className="label">AI assistant</p>
          <p className="label">Reply language</p>
          <Segmented<ReplyLang>
            value={replyLang}
            onChange={setReplyLang}
            options={[
              { value: "auto", label: "Auto" },
              { value: "en", label: "English" },
              { value: "ur", label: "اردو" },
            ]}
          />
          <p className="mt-1.5 text-xs text-ink-mute dark:text-slate-400">
            {replyLang === "auto" ? "Replies in the language of each message — English, Urdu or Roman Urdu." : replyLang === "en" ? "Always replies in English." : "ہمیشہ اردو میں جواب دے گا۔"}
          </p>
          <p className="label mt-4">Typing language</p>
          <Segmented
            value={voiceLang}
            onChange={setVoiceLang}
            options={[
              { value: "en-US", label: "English" },
              { value: "ur-PK", label: "اردو" },
            ]}
          />
          <p className="label mt-4">Voice</p>
          <p className="text-xs text-ink-mute dark:text-slate-400">
            {voice?.provider === "openai"
              ? "OpenAI voice is active: live conversation (Realtime), voice notes and spoken replies."
              : "Voice is off — the server needs OPENAI_API_KEY in backend/.env."}
          </p>
          <p className="mt-3 text-xs text-ink-mute dark:text-slate-400">
            The assistant mirrors you: typed messages get text replies, voice notes get voice-note replies, and a voice conversation is spoken.
          </p>
        </section>

        <section className="card p-5">
          <p className="label flex items-center gap-1.5">
            <Server className="h-3.5 w-3.5" /> Server
          </p>
          <Field hint={`Now using ${apiBase()}. Leave empty for the default (${DEFAULT_API_BASE}).`}>
            <Input value={server} onChange={(e) => setServer(e.target.value)} placeholder={DEFAULT_API_BASE} inputMode="url" autoCapitalize="off" autoCorrect="off" />
          </Field>
          <div className="mt-3 flex gap-2">
            <Button variant="soft" loading={testing} onClick={() => void testServer()}>
              Test & save
            </Button>
            {serverUrl && (
              <Button
                variant="ghost"
                onClick={() => {
                  setServer("");
                  setServerUrl(null);
                  resetServerVoice();
                  toast.success("Using the default server");
                }}
              >
                Reset
              </Button>
            )}
          </div>
        </section>

        <AdvertiseWithUs />

        {user && (
          <Button variant="outline" size="lg" className="w-full text-red-600 dark:text-red-400" icon={<LogOut className="h-4 w-4" />} onClick={() => void signOut()}>
            Sign out
          </Button>
        )}

        <p className="pb-4 text-center text-xs text-ink-mute">
          Watan-e-Pak AI Real Estate · {runtimeLabel[runtime]} app v{window.watanepak?.version ?? "1.0.0"}
          <br />
          Map data ©{" "}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer" className="underline">
            OpenStreetMap contributors
          </a>{" "}
          · Population © Kontur
        </p>
      </div>
    </div>
  );
}
