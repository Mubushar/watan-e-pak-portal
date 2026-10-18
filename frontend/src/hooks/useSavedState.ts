/**
 * useState that remembers its value in this browser, per signed-in user (or "guest"):
 *   const [base, setBase] = useSavedState("map.base", "streets");
 * Sets are supported. Values are saved on every change and read back on the next visit.
 * Storage failures (private mode, quota) fall back to plain in-memory state.
 */
import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useAuth } from "@/store/auth";

const PREFIX = "arz-saved";

function encode(v: unknown): string {
  return JSON.stringify(v, (_k, x) => (x instanceof Set ? { $set: [...x] } : x));
}
function decode<T>(raw: string): T {
  return JSON.parse(raw, (_k, x) => (x && typeof x === "object" && Array.isArray(x.$set) ? new Set(x.$set) : x));
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    const v = decode<T>(raw);
    // Merge saved objects over the defaults so newly added keys still get a value.
    if (fallback && typeof fallback === "object" && !(fallback instanceof Set) && !Array.isArray(fallback) && v && typeof v === "object")
      return { ...fallback, ...v };
    return v;
  } catch {
    return fallback;
  }
}

export function useSavedState<T>(name: string, initial: T | (() => T)): [T, Dispatch<SetStateAction<T>>] {
  const uid = useAuth((s) => s.user?.id) ?? "guest";
  const key = `${PREFIX}:${uid}:${name}`;
  const init = useRef(initial);
  const fallback = () => (typeof init.current === "function" ? (init.current as () => T)() : init.current);
  const [value, setValue] = useState<T>(() => read(key, fallback()));
  const keyRef = useRef(key);

  // Signing in or out switches to that user's saved choices.
  useEffect(() => {
    if (keyRef.current === key) return;
    keyRef.current = key;
    setValue(read(key, fallback()));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = useCallback<Dispatch<SetStateAction<T>>>((u) => {
    setValue((prev) => {
      const next = typeof u === "function" ? (u as (p: T) => T)(prev) : u;
      try {
        localStorage.setItem(keyRef.current, encode(next));
      } catch {
        /* private mode / quota: keep it in memory */
      }
      return next;
    });
  }, []);

  return [value, set];
}
