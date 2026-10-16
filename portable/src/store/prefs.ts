import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "system" | "light" | "dark";
export type VoiceLang = "en-US" | "ur-PK";

interface PrefsState {
  theme: Theme;
  /** User-entered backend URL; null = use the build/platform default. */
  serverUrl: string | null;
  favorites: string[];
  voiceLang: VoiceLang;
  /** Read assistant replies aloud. */
  autoSpeak: boolean;
  /** After a spoken reply, start listening again automatically. */
  handsFree: boolean;
  onboarded: boolean;
  setTheme: (t: Theme) => void;
  setServerUrl: (u: string | null) => void;
  toggleFavorite: (id: string) => void;
  setVoiceLang: (l: VoiceLang) => void;
  setAutoSpeak: (v: boolean) => void;
  setHandsFree: (v: boolean) => void;
  setOnboarded: (v: boolean) => void;
}

export const usePrefs = create<PrefsState>()(
  persist(
    (set) => ({
      theme: "system",
      serverUrl: null,
      favorites: [],
      voiceLang: "en-US",
      autoSpeak: true,
      handsFree: false,
      onboarded: false,
      setTheme: (theme) => set({ theme }),
      setServerUrl: (serverUrl) => set({ serverUrl }),
      toggleFavorite: (id) =>
        set((s) => ({ favorites: s.favorites.includes(id) ? s.favorites.filter((f) => f !== id) : [...s.favorites, id] })),
      setVoiceLang: (voiceLang) => set({ voiceLang }),
      setAutoSpeak: (autoSpeak) => set({ autoSpeak }),
      setHandsFree: (handsFree) => set({ handsFree }),
      setOnboarded: (onboarded) => set({ onboarded }),
    }),
    { name: "arzepak-app-prefs" },
  ),
);
