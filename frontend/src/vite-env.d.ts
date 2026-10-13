/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_STT_PROVIDER?: "browser" | "server";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
