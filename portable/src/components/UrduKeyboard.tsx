/**
 * Typing helpers for any text box, in English or Urdu:
 *   - Phonetic layout: with Urdu selected, a physical (PC / Mac) keyboard types Urdu
 *     letters by sound — a→ا b→ب p→پ t→ت … (Shift for the extra letters).
 *   - On-screen keyboard with English (QWERTY) and Urdu layouts — 🌐 switches between
 *     them — for touch screens, kiosks and anyone who prefers tapping.
 * Phones can also just switch their own keyboard (e.g. Gboard) to Urdu.
 */
import { useState, type KeyboardEvent, type RefObject } from "react";
import { ArrowBigUp, CornerDownLeft, Delete, Globe } from "lucide-react";
import { cn } from "@/lib/utils";

/** Phonetic Urdu layout (lower case, then Shift). Unmapped keys type as usual. */
export const PHONETIC: Record<string, string> = {
  a: "ا", b: "ب", c: "چ", d: "د", e: "ع", f: "ف", g: "گ", h: "ہ", i: "ی", j: "ج", k: "ک", l: "ل", m: "م",
  n: "ن", o: "و", p: "پ", q: "ق", r: "ر", s: "س", t: "ت", u: "ء", v: "ط", w: "و", x: "ش", y: "ے", z: "ز",
  A: "آ", C: "ث", D: "ڈ", E: "ٰ", G: "غ", H: "ح", I: "ِ", J: "ض", K: "خ", N: "ں", O: "ۃ", P: "ُ", R: "ڑ",
  S: "ص", T: "ٹ", U: "ئ", V: "ظ", W: "ؤ", X: "ژ", Y: "َ", Z: "ذ", F: "ٔ", B: "ٓ", M: "ھ", L: "ۓ", Q: "ْ",
  ",": "،", ".": "۔", "?": "؟", ";": "؛",
};

export type KeyboardLang = "en" | "ur";

const DIGITS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];

const LAYOUTS: Record<KeyboardLang, string[][]> = {
  en: [DIGITS, ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"], ["a", "s", "d", "f", "g", "h", "j", "k", "l"], ["z", "x", "c", "v", "b", "n", "m"]],
  ur: [
    DIGITS,
    ["ا", "آ", "ب", "پ", "ت", "ٹ", "ث", "ج", "چ", "ح", "خ"],
    ["د", "ڈ", "ذ", "ر", "ڑ", "ز", "ژ", "س", "ش", "ص", "ض"],
    ["ط", "ظ", "ع", "غ", "ف", "ق", "ک", "گ", "ل", "م", "ن"],
    ["ں", "و", "ہ", "ھ", "ء", "ی", "ے", "ئ", "ۃ"],
  ],
};

type Field = HTMLInputElement | HTMLTextAreaElement;

/** Insert text at the caret of a controlled input and keep the caret after it. */
export function insertAtCaret(el: Field | null, value: string, text: string, setValue: (v: string) => void) {
  const start = el?.selectionStart ?? value.length;
  const end = el?.selectionEnd ?? value.length;
  const next = value.slice(0, start) + text + value.slice(end);
  setValue(next);
  requestAnimationFrame(() => {
    if (!el) return;
    const pos = start + text.length;
    el.setSelectionRange(pos, pos);
  });
}

export function backspaceAtCaret(el: Field | null, value: string, setValue: (v: string) => void) {
  const start = el?.selectionStart ?? value.length;
  const end = el?.selectionEnd ?? value.length;
  if (start === 0 && end === 0) return;
  const from = start === end ? Math.max(0, start - [...value.slice(0, start)].slice(-1)[0]!.length) : start;
  setValue(value.slice(0, from) + value.slice(end));
  requestAnimationFrame(() => el?.setSelectionRange(from, from));
}

/**
 * onKeyDown handler: maps physical keys to Urdu letters (phonetic layout). Shortcuts
 * (Ctrl/Cmd/Alt) and keys of virtual keyboards that don't report a key pass through.
 */
export function phoneticKeyDown(e: KeyboardEvent<Field>, value: string, setValue: (v: string) => void) {
  if (e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1 || e.nativeEvent.isComposing) return;
  const mapped = PHONETIC[e.key];
  if (!mapped) return;
  e.preventDefault();
  insertAtCaret(e.currentTarget, value, mapped, setValue);
}

const keyBase =
  "flex h-10 min-w-0 flex-1 items-center justify-center rounded-lg bg-white text-ink shadow-sm transition active:scale-95 active:bg-brand-50 dark:bg-white/10 dark:text-slate-100";
const keyFn = "flex h-10 items-center justify-center gap-1.5 rounded-lg bg-black/[.06] px-3 text-xs font-semibold text-ink-soft shadow-sm transition active:scale-95 dark:bg-white/[.08] dark:text-slate-300";

/** Tappable keyboard with English and Urdu layouts. */
export function OnScreenKeyboard({
  target,
  value,
  onChange,
  lang,
  onLangChange,
  onEnter,
  className,
}: {
  target: RefObject<Field>;
  value: string;
  onChange: (v: string) => void;
  lang: KeyboardLang;
  onLangChange: (l: KeyboardLang) => void;
  /** Called by the ⏎ key (e.g. send the message). */
  onEnter?: () => void;
  className?: string;
}) {
  const [shift, setShift] = useState(false);
  const ur = lang === "ur";
  const type = (ch: string) => {
    insertAtCaret(target.current, value, ch, onChange);
    if (shift) setShift(false);
  };
  const rows = LAYOUTS[lang];
  return (
    <div
      dir={ur ? "rtl" : "ltr"}
      className={cn("select-none space-y-1.5 rounded-2xl bg-black/[.04] p-2 dark:bg-white/[.06]", className)}
      // Keep focus (and the caret) in the text box while tapping keys.
      onMouseDown={(e) => e.preventDefault()}
      role="group"
      aria-label={ur ? "Urdu on-screen keyboard" : "English on-screen keyboard"}
    >
      {rows.map((row, i) => (
        <div key={i} className="flex gap-1">
          {!ur && i === rows.length - 1 && (
            <button type="button" onClick={() => setShift((s) => !s)} className={cn(keyFn, "w-12", shift && "bg-brand-700 text-white dark:bg-brand-600")} aria-label="Shift" aria-pressed={shift}>
              <ArrowBigUp className="h-5 w-5" />
            </button>
          )}
          {row.map((ch) => {
            const out = !ur && shift ? ch.toUpperCase() : ch;
            return (
              <button key={ch} type="button" onClick={() => type(out)} className={cn(keyBase, ur ? "urdu text-lg font-semibold" : "text-base font-medium", i === 0 && "h-9 text-sm")}>
                {out}
              </button>
            );
          })}
          {i === rows.length - 1 && (
            <button type="button" onClick={() => backspaceAtCaret(target.current, value, onChange)} className={cn(keyFn, "w-12")} aria-label="Backspace">
              <Delete className={cn("h-5 w-5", ur && "-scale-x-100")} />
            </button>
          )}
        </div>
      ))}
      <div className="flex gap-1">
        <button type="button" onClick={() => onLangChange(ur ? "en" : "ur")} className={cn(keyFn, "w-20")} aria-label={ur ? "Switch to English keyboard" : "Switch to Urdu keyboard"}>
          <Globe className="h-4 w-4" /> {ur ? "EN" : "اردو"}
        </button>
        <button type="button" onClick={() => type(ur ? "،" : ",")} className={cn(keyFn, "w-10 text-base")}>
          {ur ? "،" : ","}
        </button>
        <button type="button" onClick={() => type(" ")} className={cn(keyBase, "text-xs font-semibold text-ink-mute")} aria-label="Space">
          {ur ? "اسپیس" : "space"}
        </button>
        <button type="button" onClick={() => type(ur ? "۔" : ".")} className={cn(keyFn, "w-10 text-base")}>
          {ur ? "۔" : "."}
        </button>
        <button type="button" onClick={() => type(ur ? "؟" : "?")} className={cn(keyFn, "w-10 text-base")}>
          {ur ? "؟" : "?"}
        </button>
        {onEnter && (
          <button type="button" onClick={onEnter} className={cn(keyFn, "w-14 bg-brand-700 text-white dark:bg-brand-600 dark:text-white")} aria-label="Send">
            <CornerDownLeft className={cn("h-4 w-4", ur && "-scale-x-100")} />
          </button>
        )}
      </div>
    </div>
  );
}
