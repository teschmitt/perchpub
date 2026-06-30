# PerchPub frontend

The PerchPub web UI: a **SvelteKit 2 / Svelte 5** app rendered server-side under
`@sveltejs/adapter-node`. It replaces the original Full Stack FastAPI Template
React SPA.

## Architecture (P0 foundation)

- **SSR + adapter-node.** Runs as a Node server (`node build`) on port `3000` in
  production; the browser only ever talks to this same origin.
- **BFF cookie-session auth.** Login is a server-side form action that exchanges
  credentials with the backend and stores the JWT in an `httpOnly` `pp_session`
  cookie. The token never reaches client JavaScript; `src/hooks.server.ts`
  forwards it as a `Bearer` to the backend over the internal network.
- **Two routing zones.** `src/routes/(public)` renders without a guard;
  `src/routes/(app)` is guarded server-side in `+layout.server.ts`.
- **Typed API client.** `src/lib/api/` is generated from the backend's OpenAPI
  schema via `openapi-typescript` + `openapi-fetch` — endpoint URLs are never
  hand-written.
- **Media** is served same-origin through `src/routes/media/[...path]` which
  proxies the backend `GET /api/v1/media/{object_name}` endpoint.

See `../openspec/changes/add-sveltekit-frontend-foundation/design.md` for the
architecture of record.

## Develop

```bash
npm install
npm run dev            # http://localhost:5173 ; expects the backend on :8000
```

Set `INTERNAL_API_URL` (default `http://localhost:8000`) so server-side `load`
and form actions can reach the backend.

## Regenerate the typed API client

Run against a backend whose `app.main` is importable (env loaded):

```bash
./scripts/generate-client.sh    # dumps openapi.json → src/lib/api/schema.d.ts
```

## Commands

| Task                     | Command                      |
| ------------------------ | ---------------------------- |
| Dev server (5173)        | `npm run dev`                |
| Type-check               | `npm run check`              |
| Lint (prettier + eslint) | `npm run lint`               |
| Format                   | `npm run format`             |
| Unit tests (Vitest)      | `npm run test:unit -- --run` |
| E2E tests (Playwright)   | `npm run test:e2e`           |
| Production build         | `npm run build`              |
