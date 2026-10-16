import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "light" | "dark" | "system";
export type Lang = "en" | "ur";

interface PrefsState {
  theme: Theme;
  lang: Lang;
  favorites: string[];
  compare: string[];
  recent: string[];
  assistantOpen: boolean;
  tickerPaused: boolean;
  setTheme: (t: Theme) => void;
  setLang: (l: Lang) => void;
  toggleFavorite: (id: string) => void;
  toggleCompare: (id: string) => void;
  clearCompare: () => void;
  pushRecent: (id: string) => void;
  setAssistantOpen: (v: boolean) => void;
  setTickerPaused: (v: boolean) => void;
}

export const MAX_COMPARE = 4;

export const usePrefs = create<PrefsState>()(
  persist(
    (set) => ({
      theme: "light",
      lang: "en",
      favorites: [],
      compare: [],
      recent: [],
      assistantOpen: false,
      tickerPaused: false,
      setTheme: (theme) => set({ theme }),
      setLang: (lang) => set({ lang }),
      toggleFavorite: (id) =>
        set((s) => ({ favorites: s.favorites.includes(id) ? s.favorites.filter((x) => x !== id) : [...s.favorites, id] })),
      toggleCompare: (id) =>
        set((s) => {
          if (s.compare.includes(id)) return { compare: s.compare.filter((x) => x !== id) };
          return { compare: [...s.compare, id].slice(-MAX_COMPARE) };
        }),
      clearCompare: () => set({ compare: [] }),
      pushRecent: (id) => set((s) => ({ recent: [id, ...s.recent.filter((x) => x !== id)].slice(0, 12) })),
      setAssistantOpen: (assistantOpen) => set({ assistantOpen }),
      setTickerPaused: (tickerPaused) => set({ tickerPaused }),
    }),
    { name: "arzepak-prefs", partialize: (s) => ({ ...s, assistantOpen: false }) },
  ),
);
