/// <reference types="vite/client" />

// Type augmentation cho `import.meta.env.<VITE_*>` — Vite inject vars vào
// build time, cần khai báo types để tsc compile được.
interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_WS_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
