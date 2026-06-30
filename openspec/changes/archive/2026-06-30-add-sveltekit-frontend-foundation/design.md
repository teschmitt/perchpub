# Design — SvelteKit frontend foundation

This document is the architecture of record for the whole frontend rewrite. P1–P3 reference it rather than restating it.

## Decisions (and why)

| Decision | Choice | Why |
| --- | --- | --- |
| Extend vs replace | **Replace** | The product domain is greenfield either way; only the easy non-product surface (auth/account/admin/components) would be reused. SSR + preferred stack outweigh rebuilding that bounded surface. |
| Framework | **SvelteKit 2 / Svelte 5 (runes), `adapter-node`** | SSR fits the public-browsing-first product (SEO, shareable pages, fast first paint); maintained solo in the preferred stack. |
| Product shape | **Public browsing + authed management** | Backend read endpoints (`/observation/`, `/species/`, `/station/`) already serve anonymous callers; management stays behind auth. |
| Auth | **BFF + httpOnly cookie** | Token never reaches the browser (XSS-safe), every page is SSR-able, web app is same-origin (no CORS). |
| Media | **Backend proxy endpoint + same-origin pass-through** | Bucket stays private; per-station `is_private` enforcement can drop in later; `<img>/<video>` get plain same-origin URLs. |
| Component kit | **Tailwind v4 + shadcn-svelte (bits-ui)** | Near 1:1 parity with the kit being removed; low-risk re-port. |
| API client | **`openapi-typescript` → `openapi-fetch`, generated** | Keeps "types are generated, never hand-written"; lean, ideal for server-side `load`. |
| Data layer | **SvelteKit `load` + form actions** | Native SSR + progressive-enhancement; no TanStack Query until a page proves it needs client cache. |

## Architecture

### Routing zones (file-based groups)

```
src/routes/
  +layout.svelte                 # global: theme provider, toaster
  (public)/                      # no guard, SSR
    +layout.svelte               # public nav (logo, Observations, Species, Stations, Login/Account)
    +page.svelte                 # landing
    observations/  ...           # P1
    species/       ...           # P1
    stations/      ...           # P1 (view), P2 (manage lives under (app))
  (app)/                         # guarded in +layout.server.ts
    +layout.server.ts            # requireUser()  -> redirect /login if no session
    +layout.svelte               # console shell (sidebar)
    dashboard/     ...
    stations/      ...           # P2 manage
    enroll/        ...           # P2
    account/       ...           # P2
    admin/         ...           # P3 (+ superuser guard)
  login/   +page.svelte + +page.server.ts   # form action sets cookie
  logout/  +server.ts                        # clears cookie
  media/[...path]/+server.ts                 # same-origin pass-through to backend media endpoint
```

### Auth flow (BFF)

1. **Login** — form action POSTs `username`/`password` (form-encoded) to `${INTERNAL_API_URL}/login/access-token`. On success, set cookie `pp_session` = JWT: `httpOnly`, `secure`, `sameSite=lax`, `path=/`, `maxAge` = token TTL. Redirect to the post-login target.
2. **Per-request auth** — `hooks.server.ts` reads `pp_session`; if present, sets `event.locals.session` and exposes an authed `fetch` wrapper that injects `Authorization: Bearer <jwt>` and targets `INTERNAL_API_URL`. It resolves `event.locals.user` by calling `/users/me` once per request (used by guards and nav). A backend `401` (expired/invalid token) clears the cookie and, in the `(app)` zone, redirects to `/login`.
3. **Guards** — `(app)/+layout.server.ts` redirects to `/login` when `locals.user` is null. Superuser areas (P3) additionally assert `locals.user.is_superuser` (404/redirect otherwise); the backend still 403s the data as defense-in-depth.
4. **Optional-auth public pages** — `(public)` server `load` forwards the bearer **only if a cookie exists**, so a logged-in owner sees their private stations on public pages; anonymous visitors get the public subset. No public page requires a token, and the cookie-expiry 401 handling never forces a logout from the public zone.
5. **Mutations** — SvelteKit **form actions** (run server-side with the cookie). A thin `/api/[...path]/+server.ts` proxy exists only for unavoidable client-only calls.

### Generated client

`scripts/generate-client.sh` (analog of the existing one): dump the backend `openapi.json`, run `openapi-typescript` to produce `src/lib/api/schema.d.ts`, and expose a configured `openapi-fetch` client (`src/lib/api/client.ts`) whose `baseUrl` is `INTERNAL_API_URL` on the server. Conventions to respect (from the backend): singular collection prefixes (`/station`, `/observation`) vs plural `/users`; trailing-slash sensitivity on collection routes (the typed client encodes the exact paths); the species list wrapper is `SpeciesMultiPublic`.

### Media path

`GET /api/v1/media/{object_name:path}` (backend) streams the object from the existing `garage_client`, sets `Content-Type` from the key extension, and sends `Cache-Control: public, max-age=31536000, immutable` (objects are sha-addressed, so content never changes for a key). Unknown keys → `404`. Public read in P0; the handler is structured so a per-observation/`is_private`-station visibility check can be added without changing the URL contract. The browser fetches `/media/<object_name>` (same-origin), which the SvelteKit `media/[...path]` endpoint streams from the backend.

### Deployment

`adapter-node` produces a Node server (`node build`) on `:3000`. The frontend Dockerfile's nginx stage is replaced by a Node runtime stage. `docker-compose.yml`: frontend `loadbalancer.server.port` 80→3000; add `INTERNAL_API_URL=http://backend:8000`, `ORIGIN=https://${DOMAIN}`, and adapter-node `PROTOCOL_HEADER`/`HOST_HEADER` for Traefik. The frontend Traefik router serves the **apex** `Host(`${DOMAIN}`)` (with a `www.${DOMAIN}`→apex redirect and the Let's Encrypt cert covering both), replacing the template's `dashboard.${DOMAIN}`. Drop the build-time `VITE_API_URL` arg (server uses the internal URL; public absolute URLs for OG tags/assets use `PUBLIC_SITE_URL=https://${DOMAIN}`). Dev override: `npm run dev` on 5173 with `INTERNAL_API_URL=http://localhost:8000`. The Playwright service builds the SSR image and runs against it.

## Error handling

SvelteKit `+error.svelte` + `error()`; backend `{detail}` mapped to user-facing messages; toasts via the shadcn-svelte sonner equivalent. The single cross-cutting rule: a backend `401` in `hooks.server.ts` clears `pp_session` (and redirects to `/login` only within the `(app)` zone).

## Testing

- **Vitest** — `hooks.server.ts` cookie/bearer logic, the generated-client wrapper, guard helpers.
- **Playwright** (reuse the repo's compose service) — login sets the cookie and redirects; an unauthenticated visit to an `(app)` route redirects to `/login`; an SSR public smoke page renders server-side.
- **pytest** — the media endpoint: a known key streams `200` with the right `Content-Type` and immutable cache header; an unknown key returns `404`.

## Risks / open notes

- **Public hostname (decided): apex `${DOMAIN}`.** The public-browsing app serves on the apex `${DOMAIN}` (with a `www.${DOMAIN}`→apex redirect), not the template's console-oriented `dashboard.${DOMAIN}`, so `ORIGIN`/`PUBLIC_SITE_URL` and the OG/share URLs resolve to the memorable public face. This requires a DNS record, a Traefik `Host(`${DOMAIN}`)` rule, and a Let's Encrypt cert covering the apex (+ `www`) — see task 7.2. The API stays at `api.${DOMAIN}` (the browser no longer uses it; stations keep the `:8443` mTLS edge).
- Adapter-node behind Traefik needs correct `ORIGIN`/proxy-header config or form actions fail CSRF/Origin checks — covered in tasks.
- The single OVH instance now runs a Node process (more memory than nginx static) — acceptable at this scale.
- Known backend gaps inherited, not fixed here: `GET /observation/` lacks visibility filtering; `classify-task` GETs lack auth. Flagged for a later change.
