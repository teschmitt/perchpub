## 1. Scaffold the SvelteKit app (replace the React SPA)

- [x] 1.1 Remove the React/Vite tree from `frontend/` (preserve in git history): `src/`, `index.html`, `vite.config.ts`, `tsconfig*.json`, the generated `src/client/*`, `src/components/Items/*`, FastAPI assets (`public/assets/images/fastapi-*.svg`), and the template `frontend/README.md`. Keep `tests/` (Playwright) for now — it is rewritten in task 7. *(Done as a clean wholesale replacement — the whole React tree incl. nginx/biome/openapi-ts was removed; old Playwright specs were greenfield-rewritten in task 8 rather than preserved, since they were React-specific.)*
- [x] 1.2 Scaffold a SvelteKit 2 / Svelte 5 project in `frontend/` with TypeScript, `@sveltejs/adapter-node`, Vitest, Prettier + `eslint-plugin-svelte`, and `svelte-check`. *(via `sv create`; adapter-node + config live in `vite.config.ts` per current SvelteKit.)*
- [x] 1.3 Add Tailwind v4 and initialise shadcn-svelte (bits-ui); port the theme tokens (dark default) and add the sonner toaster + theme provider in the root `+layout.svelte`. *(shadcn-svelte foundation hand-authored — `components.json`, `cn`, teal theme in `src/app.css`, `Toaster` + `ModeWatcher defaultMode="dark"` — because the v1.3 CLI blocks on an interactive preset prompt in non-TTY.)*
- [x] 1.4 Add a new `frontend/README.md` describing the SvelteKit app, dev command, and the generate-client step.

## 2. Generated typed API client

- [x] 2.1 Add `openapi-typescript` + `openapi-fetch`; write `frontend/scripts/generate-client.sh` that dumps the backend `openapi.json` and runs `openapi-typescript` to `src/lib/api/schema.d.ts`. *(openapi-typescript invoked via `npx` in the script — kept out of package.json to avoid its TS^5 peer conflict with the scaffold's TS 6, so `npm ci` stays clean.)*
- [x] 2.2 Add `src/lib/api/client.ts`: an `openapi-fetch` factory whose `baseUrl` is `INTERNAL_API_URL` and that accepts an optional bearer; export a server-side helper (`serverApiClient`) that builds a client from `event.locals`.
- [x] 2.3 Run the generator against the live backend and commit the generated `schema.d.ts`; confirmed Station/Observation/Species/ClassifyTask/Enrollment/Users types are present.

## 3. BFF cookie-session auth

- [x] 3.1 `src/routes/login/+page.server.ts`: a form action that POSTs form-encoded `username`/`password` to the backend `/login/access-token`; on success set `pp_session` (httpOnly, secure, sameSite=lax, path=/, maxAge=token TTL) and redirect; on failure return a typed form error. *(redirect target validated through `safeRedirectTarget` — local paths only, no open redirect.)*
- [x] 3.2 `src/routes/logout/+server.ts`: clear `pp_session` and redirect to `/`.
- [x] 3.3 `src/hooks.server.ts`: read `pp_session`; set `event.locals.session`; provide an authed client (injects `Authorization: Bearer`, targets `INTERNAL_API_URL`); resolve `event.locals.user` via `/users/me` once per request; on a backend `401` clear the cookie. *(Network-error degrades to anonymous without clearing the cookie, so a backend blip never 500s public pages.)*
- [x] 3.4 Type `App.Locals` (`session`, `user`) in `src/app.d.ts`.

## 4. Routing zones and guards

- [x] 4.1 Create the `(public)` group with `+layout.svelte` (public nav reflecting `locals.user`) and a placeholder SSR landing `+page.svelte`.
- [x] 4.2 Create the `(app)` group with `+layout.server.ts` (`requireUser` → redirect to `/login?redirectTo=...` when `locals.user` is null) and a console shell `+layout.svelte` (sidebar) + a placeholder `dashboard/+page.svelte`.
- [x] 4.3 Add a reusable superuser guard helper (`requireSuperuser`, used by P3 admin routes) that 404s/redirects when `!locals.user.is_superuser`.
- [x] 4.4 Implement optional-auth: `serverApiClient(locals)` forwards the bearer only when a session cookie is present, so public pages work anonymously and enriched when logged in.

## 5. Backend media endpoint

- [x] 5.1 Add `backend/app/api/routes/media.py`: `GET /media/{object_name:path}` streaming from the module-level `garage_client`, `Content-Type` from the key extension, `Cache-Control: public, max-age=31536000, immutable`; `404` for a missing key (`NoSuchKey`/`NoSuchObject` only — a missing/misconfigured bucket surfaces as a loud 5xx). Visibility seam documented for a later `is_private` check.
- [x] 5.2 Register the router in `backend/app/api/main.py` under `/api/v1`.
- [x] 5.3 `backend/tests/api/routes/test_media.py`: known key → `200` + expected content-type + immutable cache header; unknown key → `404`; missing bucket → not masked as 404.
- [x] 5.4 Ran `cd backend && bash scripts/lint.sh && bash scripts/test.sh`; green (138 passed).

## 6. Same-origin media pass-through

- [x] 6.1 `src/routes/media/[...path]/+server.ts`: streams `GET ${INTERNAL_API_URL}/api/v1/media/<path>` back to the browser, forwarding `Content-Type` + `Cache-Control`; a backend-unreachable failure maps to a clean 502. No auth in P0.
- [x] 6.2 Add a tiny `src/lib/media.ts` helper turning an observation `object_name` into a `/media/<object_name>` URL.

## 7. Deployment cutover

- [x] 7.1 Rewrite `frontend/Dockerfile`: build stage runs `npm ci && npm run build` (adapter-node); runtime stage is a Node image running `node build` on `:3000` (nginx stage + `nginx*.conf` removed); a `dev` stage runs the Vite dev server for the override.
- [x] 7.2 `docker-compose.yml` frontend service: `loadbalancer.server.port` 80→3000; apex `Host(${DOMAIN})` rule with a `www.${DOMAIN}`→apex `redirectregex` middleware (both get LE certs via `certresolver=le`); env `INTERNAL_API_URL`/`ORIGIN`/`PROTOCOL_HEADER`/`HOST_HEADER`/`PUBLIC_SITE_URL`; build-time `VITE_API_URL` dropped.
- [x] 7.3 `docker-compose.override.yml`: dev frontend runs `npm run dev` (port 5173, `target: dev`) with `INTERNAL_API_URL=http://backend:8000`; `Dockerfile.playwright` builds the SSR image (and the `playwright` service drops `VITE_API_URL` for `INTERNAL_API_URL`).
- [x] 7.4 Updated `.env.prod` `FRONTEND_HOST` to the apex and the CLAUDE.md dev-ports/commands note for the new frontend runtime. *(Note: `INTERNAL_API_URL` for the dev compose container is `http://backend:8000`, not the literal `localhost:8000` from the task text — `localhost` inside the container can't reach the backend. The live `docker compose up frontend` / apex-resolve check requires a real Docker host — this sandbox has none — so it is the remaining real-stack verification; compose YAML parses for all three files.)*

## 8. Tests and verification gate

- [x] 8.1 Vitest: `resolveSession` (cookie→bearer, 401-clears-cookie), the client factory + `serverApiClient` (optional-auth bearer-iff-session), the `requireUser`/`requireSuperuser`/`safeRedirectTarget` guards, and `mediaUrl` — 23 tests.
- [x] 8.2 Playwright: login sets `pp_session` (httpOnly) and redirects (verified against the **real backend**; also asserts a hostile `redirectTo` is not honored); an `(app)` route unauthenticated redirects to `/login`; the public landing renders server-side (asserts SSR'd HTML). *(Run locally against `npm run preview`; the compose `playwright` service config is in place but its end-to-end run needs the real stack.)*
- [x] 8.3 Ran frontend `npm run lint && npm run check && npm run test:unit` (+ Playwright) and backend `bash scripts/lint.sh && bash scripts/test.sh`; all green.
- [x] 8.4 Ran `openspec validate add-sveltekit-frontend-foundation --strict` — valid.

---

### Verification summary (sandbox has no Docker/Postgres; bootstrapped embedded Postgres + ran the SSR server directly)

- **Frontend:** `npm run lint` ✓ · `npm run check` (0 errors) ✓ · Vitest 23/23 ✓ · Playwright 4/4 ✓ (SSR render, anonymous public access, `(app)`→`/login` redirect, login→httpOnly-cookie+redirect against the **real backend** with open-redirect blocked) · adapter-node `npm run build` ✓.
- **Backend:** `bash scripts/lint.sh` ✓ · `bash scripts/test.sh` → **138 passed** ✓ (incl. 3 media-endpoint tests).
- **OpenSpec:** `openspec validate --strict` ✓. Compose YAML parses for all three files.
- **Code review:** adversarial multi-dimension review run; 3 confirmed MEDIUM findings fixed (open-redirect via `redirectTo`, hooks 500-on-backend-blip, media `NoSuchBucket` masked as 404), each re-verified.
- **Remaining real-stack checks (no Docker here):** `docker compose --env-file .env.dev up frontend` serving SSR; the apex `Host(${DOMAIN})` + `www`→apex + LE certs resolving in the prod overlay; the compose `playwright` service e2e run. P0's design flags these as the deploy-model spike to confirm in the real compose stack.
