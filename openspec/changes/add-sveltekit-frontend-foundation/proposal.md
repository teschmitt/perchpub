## Why

The committed frontend is the stock Full Stack FastAPI Template, essentially untouched for PerchPub: a search for `perch/bird/feeder/station/observation/species/classify/enrollment` across `frontend/src` returns zero matches. It covers only the account/auth surface that overlaps the template (login, signup, password reset, `/settings`, `/admin`), runs that through a **stale generated client** (`src/client/*` knows only Items/Login/Users/Utils — no Station/Observation/Species/ClassifyTask/Enrollment types, and there is no committed `openapi.json`), and still ships a fully-wired `/items` feature for a resource the backend deleted (that route breaks at runtime). None of the actual product — browsing observations, the species catalog, station management, enrollment — exists.

Rather than extend the React/TanStack chassis, this effort **replaces** the frontend with a SvelteKit (SSR, `adapter-node`) application. The product domain is greenfield either way, so the only thing "extend" would have saved is the easy non-product surface (auth, account, admin, component kit). SvelteKit's server-side rendering is a direct fit for the chosen **public-browsing-first** product shape (SEO, shareable observation pages with preview cards, fast first paint), and a `backend-for-frontend` (BFF) auth model removes the cross-origin/localStorage-token setup the SPA carries today.

This change (P0) builds **only the foundation** — no product pages yet. It establishes the SvelteKit app, the BFF cookie-session auth, the two routing zones, the generated typed client, the deployment cutover, and the one backend change everything visual depends on: a browser-facing media endpoint. P1–P3 (tracked as separate changes) build the product on top.

## What Changes

- **Replace the frontend.** A new SvelteKit 2 / Svelte 5 app (`adapter-node`) replaces the Vite/React static SPA in `frontend/`. The old React tree is removed (preserved in git history); the `/items` cruft and FastAPI branding go with it.
- **BFF + httpOnly cookie auth.** Login is a SvelteKit form action that POSTs `/login/access-token` server-side and sets an httpOnly/Secure/SameSite=Lax `pp_session` cookie. `hooks.server.ts` reads the cookie and forwards the JWT as a `Bearer` to the **internal** backend (`backend:8000`); the browser never holds the token. The web app becomes same-origin (no browser CORS; the public `api.*` browser edge is no longer depended on — stations keep the `:8443` mTLS edge).
- **Two routing zones.** A `(public)` group (no guard, SSR) and an `(app)` group (server-side auth guard in `+layout.server.ts`, plus a superuser guard for admin areas). Public pages use optional-auth: server `load` forwards the bearer only if a cookie is present.
- **Generated typed client.** `openapi-typescript` + `openapi-fetch` generated from the live backend `openapi.json` via a `scripts/generate-client.sh` analog. No hand-written API URLs.
- **Backend media endpoint.** New `GET /api/v1/media/{object_name:path}` streams objects from S3 (existing minio `garage_client`), with content-addressed immutable caching. The browser reaches it same-origin through a SvelteKit `/media/[...path]` pass-through.
- **Deployment cutover.** Dockerfile builds `adapter-node` and serves on `:3000` (replacing the nginx-static image); the Traefik frontend router serves the **apex** `Host(`${DOMAIN}`)` on port 3000 (with a `www.${DOMAIN}`→apex redirect and a cert covering both), replacing the template's `dashboard.${DOMAIN}`:80; `INTERNAL_API_URL` + adapter-node proxy headers are added; build-time `VITE_API_URL` is dropped. Dev (`npm run dev` on 5173) and the Playwright compose service are updated.
- **Out of scope (non-goals):** any product pages (observations, species, stations, enrollment, account, admin) — those are P1–P3; fixing the known backend gaps (`GET /observation/` has no visibility filtering; `classify-task` GETs have no auth); retiring the `api.*` browser edge; a station-coordinate map UI.

## Capabilities

### New Capabilities
- `web-frontend`: the SvelteKit SSR application shell — its rendering model, BFF cookie-session authentication, the public/authed routing zones and their server-side guards, optional-authentication on public pages, and the generated typed API client.
- `media-serving`: how feeder media (referenced only by an S3 `object_name` on observations) is retrieved by a browser — a backend retrieval endpoint and same-origin delivery to the SvelteKit app.

### Modified Capabilities
- None.

## Impact

- **Frontend:** `frontend/` is replaced wholesale (new SvelteKit app; React tree, `src/client/*`, `src/components/Items/*`, FastAPI branding/assets, and the template README removed).
- **Backend:** new `backend/app/api/routes/media.py` + registration in `backend/app/api/main.py`; pytest coverage under `backend/tests/api/routes/`. No model/migration changes.
- **Deploy:** `frontend/Dockerfile` (Node SSR multi-stage, replaces nginx stage), `docker-compose.yml` frontend service port 80→3000 + `INTERNAL_API_URL`/`ORIGIN` env, `docker-compose.override.yml` dev args, `Dockerfile.playwright`. No Traefik dynamic-config change beyond the frontend router port.
- **Settings:** no new backend config field (media uses the existing Garage settings). Frontend gains `INTERNAL_API_URL`, `PUBLIC_SITE_URL`, and adapter-node `ORIGIN` env.
- **Dependencies:** removes the React/Vite/TanStack/shadcn stack; adds SvelteKit, `@sveltejs/adapter-node`, Tailwind v4, shadcn-svelte (bits-ui), `openapi-typescript`, `openapi-fetch`, Vitest. Playwright is retained.
