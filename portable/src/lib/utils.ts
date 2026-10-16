import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Resolve a file in public/ relative to the app (works under Capacitor, Electron and Vite). */
export function asset(path: string): string {
  return `${import.meta.env.BASE_URL}${path.replace(/^\//, "")}`;
}

/** True when the string contains Arabic-script (Urdu) characters. */
export function isUrdu(text: string): boolean {
  return /[\u0600-\u06FF]/.test(text);
}
