## 1. Scaffold the SvelteKit app (replace the React SPA)

- [ ] 1.1 Remove the React/Vite tree from `frontend/` (preserve in git history): `src/`, `index.html`, `vite.config.ts`, `tsconfig*.json`, the generated `src/client/*`, `src/components/Items/*`, FastAPI assets (`public/assets/images/fastapi-*.svg`), and the template `frontend/README.md`. Keep `tests/` (Playwright) for now — it is rewritten in task 7.
- [ ] 1.2 Scaffold a SvelteKit 2 / Svelte 5 project in `frontend/` with TypeScript, `@sveltejs/adapter-node`, Vitest, Prettier + `eslint-plugin-svelte`, and `svelte-check`.
- [ ] 1.3 Add Tailwind v4 and initialise shadcn-svelte (bits-ui); port the theme tokens (dark default) and add the sonner toaster + theme provider in the root `+layout.svelte`.
- [ ] 1.4 Add a new `frontend/README.md` describing the SvelteKit app, dev command, and the generate-client step.

## 2. Generated typed API client

- [ ] 2.1 Add `openapi-typescript` + `openapi-fetch`; write `frontend/scripts/generate-client.sh` that dumps the backend `openapi.json` (from a running backend or `python -c "import app.main; ..."`) and runs `openapi-typescript` to `src/lib/api/schema.d.ts`.
- [ ] 2.2 Add `src/lib/api/client.ts`: an `openapi-fetch` factory whose `baseUrl` is `INTERNAL_API_URL` and that accepts an optional bearer; export a server-side helper that builds a client from `event.locals`.
- [ ] 2.3 Run the generator against the live backend and commit the generated `schema.d.ts`; confirm Station/Observation/Species/ClassifyTask/Enrollment/Users types are present.

## 3. BFF cookie-session auth

- [ ] 3.1 `src/routes/login/+page.server.ts`: a form action that POSTs form-encoded `username`/`password` to `${INTERNAL_API_URL}/login/access-token`; on success set `pp_session` (httpOnly, secure, sameSite=lax, path=/, maxAge=token TTL) and redirect; on failure return a typed form error.
- [ ] 3.2 `src/routes/logout/+server.ts`: clear `pp_session` and redirect to `/`.
- [ ] 3.3 `src/hooks.server.ts`: read `pp_session`; set `event.locals.session`; provide an authed fetch wrapper (injects `Authorization: Bearer`, targets `INTERNAL_API_URL`); resolve `event.locals.user` via `/users/me` once per request; on a backend `401` clear the cookie.
- [ ] 3.4 Type `App.Locals` (`session`, `user`) in `src/app.d.ts`.

## 4. Routing zones and guards

- [ ] 4.1 Create the `(public)` group with `+layout.svelte` (public nav: logo, Observations, Species, Stations, Login/Account button reflecting `locals.user`) and a placeholder SSR landing `+page.svelte`.
- [ ] 4.2 Create the `(app)` group with `+layout.server.ts` (`requireUser` → redirect to `/login?redirectTo=...` when `locals.user` is null) and a console shell `+layout.svelte` (sidebar) + a placeholder `dashboard/+page.svelte`.
- [ ] 4.3 Add a reusable superuser guard helper (used by P3 admin routes) that 404s/redirects when `!locals.user.is_superuser`.
- [ ] 4.4 Implement optional-auth: a `load` helper that forwards the bearer only when a cookie exists, so public pages work anonymously and enriched when logged in.

## 5. Backend media endpoint

- [ ] 5.1 Add `backend/app/api/routes/media.py`: `GET /media/{object_name:path}` that streams the object from the module-level `garage_client` (mirror `uploads.py` client construction), sets `Content-Type` from the key extension, and sends `Cache-Control: public, max-age=31536000, immutable`; return `404` for a missing key. Structure the handler so an `is_private` visibility check can be added later without changing the URL.
- [ ] 5.2 Register the router in `backend/app/api/main.py` under `/api/v1`.
- [ ] 5.3 `backend/tests/api/routes/test_media.py`: a seeded/known object key returns `200` with the expected content-type and immutable cache header; an unknown key returns `404`.
- [ ] 5.4 Run `cd backend && bash scripts/lint.sh && bash scripts/test.sh`; confirm green.

## 6. Same-origin media pass-through

- [ ] 6.1 `src/routes/media/[...path]/+server.ts`: stream `GET ${INTERNAL_API_URL}/api/v1/media/<path>` back to the browser, forwarding `Content-Type` and `Cache-Control`. No auth required in P0.
- [ ] 6.2 Add a tiny `src/lib/media.ts` helper turning an observation `object_name` into a `/media/<object_name>` URL.

## 7. Deployment cutover

- [ ] 7.1 Rewrite `frontend/Dockerfile`: build stage runs `npm ci && npm run build` (adapter-node); runtime stage is a Node image running `node build` on `:3000` (remove the nginx stage and `nginx*.conf`).
- [ ] 7.2 `docker-compose.yml` frontend service: `loadbalancer.server.port` 80→3000; change the router rule to the **apex** `Host(`${DOMAIN}`)` with a `www.${DOMAIN}`→apex redirect middleware, replacing the template's `Host(`dashboard.${DOMAIN}`)`, and ensure the Let's Encrypt cert covers the apex (+ `www`); add env `INTERNAL_API_URL=http://backend:8000`, `ORIGIN=https://${DOMAIN}`, `PROTOCOL_HEADER=X-Forwarded-Proto`, `HOST_HEADER=X-Forwarded-Host`, `PUBLIC_SITE_URL=https://${DOMAIN}`; drop the build-time `VITE_API_URL` arg.
- [ ] 7.3 `docker-compose.override.yml`: dev frontend runs `npm run dev` (port 5173) with `INTERNAL_API_URL=http://localhost:8000`; update `Dockerfile.playwright` to build/run the SSR image.
- [ ] 7.4 Update `.env.dev`/`.env.prod` and CLAUDE.md dev-ports/commands notes for the new frontend runtime; confirm `docker compose --env-file .env.dev up frontend` serves SSR and the apex `${DOMAIN}` route resolves in prod compose.

## 8. Tests and verification gate

- [ ] 8.1 Vitest: `hooks.server.ts` cookie→bearer logic, the client factory, the optional-auth and guard helpers.
- [ ] 8.2 Playwright (compose service): login sets `pp_session` and redirects; visiting an `(app)` route unauthenticated redirects to `/login`; the public landing renders server-side (assert SSR'd HTML, not a client-only shell).
- [ ] 8.3 Run frontend `npm run lint && npm run check && npm run test` and backend `bash scripts/lint.sh && bash scripts/test.sh`; confirm all green.
- [ ] 8.4 Run `openspec validate add-sveltekit-frontend-foundation --strict` and confirm the change validates.
