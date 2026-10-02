/// <reference types="vite/client" />

/**
 * Typed build-time configuration.
 *
 * Only `VITE_`-prefixed variables reach the bundle, and the two names mean
 * different things — see `.env.example`:
 *
 * - `VITE_API_ORIGIN` is compiled into the client and prefixes every API call.
 *   Empty means same-origin, which is the default and what the dev server and
 *   the production nginx config both expect.
 * - `VITE_BACKEND_ORIGIN` is read by `vite.config.ts` for the dev proxy and is
 *   deliberately *not* part of the client environment.
 */
interface ImportMetaEnv {
  readonly VITE_API_ORIGIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
