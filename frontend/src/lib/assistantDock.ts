/**
 * Where the AI assistant docks: the Map page offers a slot beside the map (wide screens) so the
 * chat sits next to the map instead of floating over its tools; everywhere else it floats.
 */
import { useSyncExternalStore } from "react";

let dock: HTMLElement | null = null;
const subs = new Set<() => void>();
const subscribe = (fn: () => void) => {
  subs.add(fn);
  return () => {
    subs.delete(fn);
  };
};

/** The Map page's slot element (null when the page closes). */
export function setAssistantDock(el: HTMLElement | null) {
  if (el === dock) return;
  dock = el;
  subs.forEach((f) => f());
}
export const useAssistantDock = () => useSyncExternalStore(subscribe, () => dock);

/** Wide enough to dock the chat beside the map. */
export const DOCK_QUERY = "(min-width: 1024px)";
export function useWideScreen(): boolean {
  return useSyncExternalStore(
    (fn) => {
      const m = window.matchMedia(DOCK_QUERY);
      m.addEventListener("change", fn);
      return () => m.removeEventListener("change", fn);
    },
    () => window.matchMedia(DOCK_QUERY).matches,
  );
}
