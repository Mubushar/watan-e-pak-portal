/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_API_TARGET?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Bridge exposed by electron/preload.cjs (desktop builds only). */
interface Window {
  watanepak?: { isElectron: true; platform: string; version: string };
}
