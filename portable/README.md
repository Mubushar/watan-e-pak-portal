# Arz-e-Pak portable app

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
* **Voice + text AI assistant**: talk or type in English, Urdu or Roman Urdu. It
  understands requests on the device, for example "3 bed 10 marla house in Lahore under 5
  crore" or "I want to sell my 1 kanal plot in DHA Islamabad for 3.5 crore". It answers
  with real listings and buttons that do the next step, such as opening the results or a
  **pre-filled listing form**. Replies can be read aloud. *Conversation mode* keeps
  listening after each reply, so you can use it hands-free. You can also fill the
  listing wizard's first step by voice.
* Light/dark theme, offline fallback (sample listings), configurable server URL.

## Backend endpoints used

The app talks to the same FastAPI backend as the portal (`backend/`):

| Feature | Endpoints |
| --- | --- |
| Auth | `POST /auth/signup` (no password), `/auth/verify-otp`, `/auth/resend-otp`, `/auth/otp/request`, `/auth/otp/verify`, `/auth/logout` |
| Browse | `GET /search`, `/properties`, `/properties/{id}`, `/cities`, `/hierarchy` |
| My listings | `GET/POST /me/listings`, `PUT/DELETE /me/listings/{id}`, `POST /me/listings/{id}/photos`, `GET /media/uploads/{file}` |
| Enquiries | `POST /crm/leads` |
| AI | `POST /v1/chat/completions`, `GET /rag/search`, `GET /ai/capabilities`, `POST /ai/transcribe` |

The backend has CORS enabled (override it with `PORTAL_CORS_ORIGINS`), so the desktop app
and any separately hosted build can call it. On Android/iOS, requests go through
Capacitor's native HTTP.

## Develop

```bash
cd backend && uv run python main.py          # API on http://127.0.0.1:8000
cd portable && npm install && npm run dev     # app on http://localhost:5174 (proxies /api)
```

Demo OTPs: by default the backend returns the code in the response
(`PORTAL_AUTH_EXPOSE_OTP=1`). The app shows it in a "Dev mode" hint. Turn this off in
production and connect a real SMS/e-mail provider.

### Desktop (Windows / macOS)

```bash
npm run desktop:dev      # Electron + Vite hot reload
npm run desktop:win      # release/Arz-e-Pak Setup 1.0.0.exe + portable exe
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

## Voice engines

| Platform | Speech-to-text | Text-to-speech |
| --- | --- | --- |
| Android / iOS | On-device recognizer (`@capacitor-community/speech-recognition`) | Native voices (`@capacitor-community/text-to-speech`) |
| Browser (Chrome, Edge, Safari) | Web Speech API | `speechSynthesis` |
| Windows / macOS app | Records the mic and sends the audio to `POST /ai/transcribe`, which forwards it to the configured LLM's `/audio/transcriptions` (needs `PORTAL_LLM_BASE_URL`; model `PORTAL_STT_MODEL`, default `whisper-1`) | `speechSynthesis` (OS voices) |

Without an upstream LLM, the assistant still works. It understands requests on the
device and answers from the portal's own data through the RAG fallback. With
`PORTAL_LLM_BASE_URL` set, replies come from the LLM, grounded on the listings the app
found.

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
