/**
 * Android phone sign-in helpers (native plugins in android/…/pk/watanepak/app). Neither needs a
 * phone or SMS permission, and both act only on the user's own choice:
 *
 * - pickDeviceNumber(): Google's Phone Number Hint picker lists the numbers of this phone's
 *   SIM(s); the user taps one (or cancels). It is a suggestion — the SMS code proves the number.
 * - waitForSmsCode(): SMS User Consent — when the code SMS arrives Android asks "Allow Watan-e-Pak
 *   to read this message?"; only an allowed message is read and its code filled in.
 *
 * iOS offers the code from Messages above the keyboard (autocomplete="one-time-code") and the
 * web/desktop apps have the user type it, so both helpers are no-ops there.
 */
import { Capacitor, registerPlugin } from "@capacitor/core";

interface PhoneNumberHintPlugin {
  pick(): Promise<{ phoneNumber: string }>;
}

interface SmsUserConsentPlugin {
  waitForCode(): Promise<{ message: string }>;
  cancel(): Promise<void>;
}

const PhoneNumberHint = registerPlugin<PhoneNumberHintPlugin>("PhoneNumberHint");
const SmsUserConsent = registerPlugin<SmsUserConsentPlugin>("SmsUserConsent");

export const isAndroidApp = Capacitor.isNativePlatform() && Capacitor.getPlatform() === "android";

/** The number the user picked from this phone's SIMs (E.164, e.g. "+923001234567"), or null. */
export async function pickDeviceNumber(): Promise<string | null> {
  if (!isAndroidApp) return null;
  try {
    const { phoneNumber } = await PhoneNumberHint.pick();
    return phoneNumber || null;
  } catch {
    return null; // cancelled, or no SIM number known to Google Play services
  }
}

/** The 6-digit code in an SMS such as "Watan-e-Pak: 123456 is your code to sign in…". */
export function codeFromSms(message: string, length = 6): string | null {
  return message.match(new RegExp(`(?:^|\\D)(\\d{${length}})(?!\\d)`))?.[1] ?? null;
}

/**
 * Wait (up to 5 minutes) for the code SMS and pass its code to `onCode` once the user allows it.
 * Returns a function that stops waiting.
 */
export function waitForSmsCode(onCode: (code: string) => void): () => void {
  if (!isAndroidApp) return () => {};
  let active = true;
  SmsUserConsent.waitForCode()
    .then(({ message }) => {
      const code = codeFromSms(message);
      if (active && code) onCode(code);
    })
    .catch(() => {}) // declined, timed out or replaced: the user can still type the code
    .finally(() => (active = false));
  return () => {
    if (!active) return;
    active = false;
    void SmsUserConsent.cancel().catch(() => {});
  };
}
