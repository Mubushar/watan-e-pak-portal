# Watan-e-Pak portable app

One React codebase that ships as a native app on **Android**, **iOS**, **Windows** and
**macOS** (and Linux / the browser), using the same brand theme as the web portal in
`frontend/`.

| Platform | Wrapper | Output |
| --- | --- | --- |
| Android | [Capacitor 8](https://capacitorjs.com) — `android/` | APK / AAB via Android Studio |
| iOS | Capacitor 8 (CocoaPods) — `ios/` | IPA via Xcode (needs a Mac) |
| Windows | Electron — `electron/` | NSIS installer + portable `.exe` |
| macOS | Electron | `.dmg` / `.zip` (build on a Mac) |
| Web | Vite | `dist/` |

## What it does

* **Passwordless sign-up / sign-in** with a one-time code sent to a **mobile number or
  e-mail**. Sign-up asks for a role: buyer, seller, investor, agent, landlord or tenant.
  The home screen and AI suggestions adapt to the role.
* **Browse listings**: home feed (featured, cities, just listed), Explore with filters,
  property details with a photo gallery, save, share and "Request a call" (creates a CRM
  lead for the listing's agent).
* **Create and manage listings** (any signed-in role): a 5-step wizard (describe →
  location → size & price → photos → review) with camera/gallery photo upload. My
  Listings lets you edit, mark sold/rented, re-list or delete.
* **Voice + text AI assistant** that mirrors the user: a typed message gets a text reply,
  a voice note gets a voice-note reply, and a voice conversation is spoken. Every reply
  is in the language of the user's message: English, Urdu (اردو) or Roman Urdu. It
  understands requests in all three, for example "3 bed 10 marla house in Lahore under 5
  crore", "لاہور میں 10 مرلہ گھر 5 کروڑ تک" or "meri listings dikhao". It answers with real
  listings and buttons that do the next step, such as opening the results or a
  **pre-filled listing form**. You can also fill the listing wizard's first step by voice.
* The assistant uses the backend's shared prompt, knowledge base and the user's memory
  (`POST /ai/context`): signed-in users' preferences (budget, area, size …) carry over
  between conversations, and it can `remember` what the user asks it to. It runs
  independent tool calls in parallel.
* Light/dark theme, offline fallback (sample listings), configurable server URL.

## Backend endpoints used

The app talks to the same FastAPI backend as the portal (`backend/`):

| Feature | Endpoints |
| --- | --- |
| Auth | `POST /auth/signup` (no password), `/auth/verify-otp`, `/auth/resend-otp`, `/auth/otp/request`, `/auth/otp/verify`, `/auth/logout`, `GET /auth/me` (refreshes the signed-in user on start) |
| Browse | `GET /search`, `/properties`, `/properties/{id}`, `/cities`, `/hierarchy` |
| My listings | `GET/POST /me/listings`, `PUT/DELETE /me/listings/{id}`, `POST /me/listings/{id}/photos`, `GET /media/uploads/{file}` |
| Enquiries | `POST /crm/leads` |
| AI (OpenAI) | `POST /v1/chat/completions`, `POST /ai/context` (shared prompt + knowledge + memory), `POST /ai/turn`, `POST /ai/knowledge/search`, `POST /ai/web-lookup`, `POST /me/memory`, `GET /rag/search`, `GET /ai/capabilities`, `GET /ai/tools`, `POST /ai/realtime/session`, `POST /ai/transcribe`, `POST /ai/speak` |

The backend allows every origin in development, so the desktop app and any separately
hosted build can call it. In production (`PORTAL_ENV=production`) list the origins in
`PORTAL_CORS_ORIGINS`: the desktop app's is `app://watanepak`, plus the web build's domain. On
Android/iOS, requests go through Capacitor's native HTTP and need no CORS entry.

An expired session signs the user out with a *Sign in* prompt. Sign-up as an agent creates
a normal account until an administrator approves the agent role; the sign-up screen says
so. Markdown links in the chat open only `http(s)`, `mailto`, `tel` and relative URLs.

## Develop

```bash
cd backend && uv run python main.py          # API on http://127.0.0.1:8000
cd portable && npm install && npm run dev     # app on http://localhost:5174 (proxies /api)
```

**OTP delivery:** until the backend has an SMS/e-mail provider configured, codes are not
actually sent. The app shows a "Test mode — nothing was sent" hint with the code. To send
real codes by e-mail (SMTP) and SMS (your own Android gateway phone, Twilio or a bulk-SMS
gateway), copy `backend/.env.example` to `backend/.env` and fill it in (see Administration
Guide §4.4).

**Phone sign-in:** the user enters the full number with country code and ticks the SMS
consent box before a code can be sent (the API refuses phone codes without consent). On
Android, *Use a number from this phone* opens Google's Phone Number Hint picker
(`PhoneNumberHintPlugin.java`), and when the code SMS arrives Android asks before the app
reads it, then fills the code in (`SmsUserConsentPlugin.java`, SMS User Consent API).
Neither needs a phone or SMS permission. iOS offers the code above the keyboard.

### Desktop (Windows / macOS)

```bash
npm run desktop:dev      # Electron + Vite hot reload
npm run desktop:win      # release/Watan-e-Pak Setup 1.0.0.exe + portable exe
npm run desktop:mac      # release/*.dmg — run on macOS (signing/notarization: set CSC_* env vars)
```

### Android

Requirements: Android Studio (Otter or newer), **JDK 21**, Android SDK 36. The project's
Gradle 8.14 can't run on Java 25, which is what newer Android Studio builds bundle. In
that case set *Settings → Build Tools → Gradle → Gradle JDK* to a JDK 21, or set
`JAVA_HOME` to one for command-line builds.

```bash
npm run android:open     # build web, sync, open Android Studio → Run
npm run android:run      # or run straight on a connected device/emulator
```

### iOS

Requirements: macOS, Xcode 26+, CocoaPods.

```bash
npm run mobile:sync && (cd ios/App && pod install)
npm run ios:open         # opens Xcode → pick a team → Run
```

### Pointing builds at your server

* Bake it in: `VITE_API_BASE=https://api.example.pk npm run build`.
* Or change it in the app under **Profile → Server** (stored on the device).
* Defaults: the Vite proxy (`/api`) in the browser, `http://10.0.2.2:8000` on the Android
  emulator, and `http://127.0.0.1:8000` elsewhere. A phone on your Wi-Fi needs your PC's
  LAN address, for example `http://192.168.1.20:8000`. Start the backend with
  `--host 0.0.0.0` for that.

Development builds allow plain `http://` (Android `usesCleartextTraffic`, iOS
`NSAllowsLocalNetworking`). Use HTTPS for production and remove those exceptions.

## How the assistant replies

The assistant answers the way the user asked:

| User sends | Assistant replies with |
| --- | --- |
| A typed message | A text message (nothing is played). The 🔊 Listen link reads it on request. |
| A voice note (🎤 when the box is empty; tap ➤ to send, 🗑 to discard) | A voice note (play button and audio, plus the text), played once automatically. |
| A voice conversation (🎧) | Spoken answers. One tap starts it; it listens, answers, then listens again until the user taps ■. **Let me talk** cuts an answer short. Three silent turns in a row pause it. |

**Language:** the reply-language button in the assistant header (also in Profile) is
your choice. **Auto**, the default, replies in the language of each message: Urdu script,
Roman Urdu or English, detected per message (`src/lib/lang.ts`). **EN** or **اردو** always
replies in that language. A message with no language clue,
like "ok" or "5 crore", keeps the conversation's language. Spoken Roman-Urdu replies use
Urdu script so the Urdu voice pronounces them correctly.

**Follow-ups** refine the previous search. "Houses in Lahore" → "10 marla" → "under 5
crore" → "and in Karachi?" keeps the type, size and budget and changes only the city.

**Typing in Urdu:** the **EN | اردو** switch next to the message box sets the typing
language. It also sets the greeting and the on-device speech-recognition language.
- In اردو mode a PC or Mac keyboard types Urdu phonetically (`src/components/UrduKeyboard.tsx`).
  Letters map by sound, for example a=ا b=ب p=پ t=ت j=ج c=چ d=د r=ر s=س x=ش k=ک g=گ l=ل m=م
  n=ن w/o=و h=ہ i=ی y=ے. Shift gives the extra letters: T=ٹ D=ڈ R=ڑ N=ں M=ھ A=آ H=ح K=خ S=ص.
- ⌨ (in the message box, in both languages) opens the on-screen keyboard. It has English
  (QWERTY, with Shift) and Urdu layouts, number keys, punctuation, backspace, and ⏎ to
  send. 🌐 switches the layout and the typing language together. While it's open the
  device's own keyboard stays hidden. Choosing اردو on a touch screen opens it
  automatically, because phone keyboards don't report letter keys. You can also switch
  the phone's own keyboard to Urdu.

### OpenAI voice

All AI runs on OpenAI through the backend (`OPENAI_API_KEY` in `backend/.env`). The key
never ships in the app.

| Mode | How it works |
| --- | --- |
| **Live conversation** (🎧) | OpenAI **Realtime API** (`gpt-realtime-2.1-mini`), speech-to-speech over WebRTC (`src/lib/realtime.ts`). Natural, low-latency talk that you can interrupt. Captions of both sides appear in the chat. The agent calls tools: it searches listings, opens details, reads your listings and drafts a new listing, and the results appear as cards and buttons. Mute and hang-up controls are on screen. |
| **Voice note** (🎤) | Your recording goes to OpenAI speech-to-text (`gpt-transcribe`; Urdu in Urdu script). The reply comes from the chat model and is returned as a voice note (`gpt-4o-mini-tts`). |
| **Typed message** | The OpenAI chat model (`gpt-6-luna`) replies in text. 🔊 Listen reads it aloud with the OpenAI voice. |

The voice is the same everywhere: `OPENAI_VOICE` (default `marin`), or your own
`OPENAI_VOICE_ID`. Microphone access works in Chrome, Edge and Safari, in the desktop
app, and in the Android and iOS apps (WebRTC plus the microphone permission).

## Layout

```
src/
  lib/        api (fetch + offline snapshot), config (server URL), intent (NL → filters/drafts),
              assistant (reply engine + chat store), voice (STT/TTS per platform), format, images
  store/      auth (session), prefs (theme, voice, server, favourites)
  components/ ui kit (portal classes), AppShell (tab bar / side rail), PropertyCard, Markdown
  screens/    Welcome, SignIn, SignUp, Home, Explore, PropertyDetail, Assistant,
              MyListings, ListingForm, Saved, Profile
electron/     main.cjs (app:// protocol, mic permission), preload.cjs
android/ ios/ native projects (Capacitor)
assets/       source logo for `npm run assets` (icons + splash screens)
```

The theme tokens in `tailwind.config.js` and the component classes in `src/index.css`
are copied from `frontend/`. Change both together to keep the apps identical.

## Docker browser build

The `portable/Dockerfile` builds and serves the browser version of the app. Run the full stack from the repository root with `docker compose up --build`; it is available at <http://localhost:8081> and proxies API and media requests to the backend. The container build uses `/api` as its backend base so it works behind the Compose Nginx proxy.

This container is the browser build. Use the existing Electron and Capacitor build commands above to produce Windows/macOS installers or Android/iOS packages.
