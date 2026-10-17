import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "system" | "light" | "dark";
export type VoiceLang = "en-US" | "ur-PK";
/** Reply language: "auto" mirrors each message; "en" / "ur" force a language. */
export type ReplyLang = "auto" | "en" | "ur";

interface PrefsState {
  theme: Theme;
  /** User-entered backend URL; null = use the build/platform default. */
  serverUrl: string | null;
  favorites: string[];
  voiceLang: VoiceLang;
  replyLang: ReplyLang;
  onboarded: boolean;
  setTheme: (t: Theme) => void;
  setServerUrl: (u: string | null) => void;
  toggleFavorite: (id: string) => void;
  setVoiceLang: (l: VoiceLang) => void;
  setReplyLang: (v: ReplyLang) => void;
  setOnboarded: (v: boolean) => void;
}

export const usePrefs = create<PrefsState>()(
  persist(
    (set) => ({
      theme: "system",
      serverUrl: null,
      favorites: [],
      voiceLang: "en-US",
      replyLang: "auto",
      onboarded: false,
      setTheme: (theme) => set({ theme }),
      setServerUrl: (serverUrl) => set({ serverUrl }),
      toggleFavorite: (id) =>
        set((s) => ({ favorites: s.favorites.includes(id) ? s.favorites.filter((f) => f !== id) : [...s.favorites, id] })),
      setVoiceLang: (voiceLang) => set({ voiceLang }),
      setReplyLang: (replyLang) => set({ replyLang }),
      setOnboarded: (onboarded) => set({ onboarded }),
    }),
    { name: "arzepak-app-prefs" },
  ),
);
