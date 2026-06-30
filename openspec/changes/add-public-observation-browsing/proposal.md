## Why

P0 (`add-sveltekit-frontend-foundation`) built the SvelteKit shell — the BFF cookie auth, the `(public)`/`(app)` zones, the generated typed client, and the `/media/{object_name}` path — but **no product pages**. This change (P1) builds the public, anonymous-readable product surface: the part of PerchPub a visitor or a search engine sees without logging in. It is the reason the foundation chose SSR (SEO, fast first paint, shareable observation cards), so it is the first product phase.

The backend read endpoints needed here already serve anonymous callers: `GET /observation/`, `GET /observation/{id}`, `GET /species/`, `GET /species/{id}` require no auth, and `GET /station/` / `GET /station/{id}` use optional-user visibility (anonymous sees public stations; a logged-in owner additionally sees their own private ones — see `backend/app/api/routes/stations.py:24-76`). So P1 is frontend-only: SSR pages over the generated client, no backend changes.

**Depends on `add-sveltekit-frontend-foundation` (P0) being built first** — every page here lives in the `(public)` zone, renders via server `load`, uses the generated typed client, applies optional-auth bearer forwarding, and renders media through `/media/{object_name}`, all of which P0 establishes. Owner-facing station CRUD (create/edit/delete, enrollment) is **out of scope** here and arrives in P2; this phase delivers public VIEW only.

## What Changes

- **Real landing page.** Replace the P0 placeholder landing (`(public)/+page.svelte`) with a server-rendered page showing the most recent observations (a bounded slice of `GET /observation/`), each linking to its detail page.
- **Observation feed.** A paginated `(public)/observations/` list, server-rendered from `GET /observation/` (`skip`/`limit`), each row a media thumbnail rendered via `/media/{object_name}` plus species, station, and confidence, linking to detail.
- **Observation detail.** A server-rendered `(public)/observations/[id]/` page from `GET /observation/{id}`, rendering the media (image or short video) via `/media/{object_name}`, showing the classified species, capturing station, `observed_at`, and `confidence_score`, and emitting Open Graph / share-preview `<meta>` tags so the URL unfurls into a card.
- **Species catalog.** A `(public)/species/` list from `GET /species/` (respecting the `SpeciesMultiPublic` `{data, count}` wrapper) and a `(public)/species/[id]/` detail from `GET /species/{id}`. Note `SpeciesPublic` is lean (`id`, `scientific_name` only) — there is no per-species observations field or endpoint, so cross-linking a species to its observations is out of scope here.
- **Public station list + detail.** A `(public)/stations/` list from `GET /station/` and `(public)/stations/[id]/` detail from `GET /station/{id}`, both with optional-auth bearer forwarding so an anonymous visitor sees only public stations while a logged-in owner additionally sees their own private stations. A private station the caller may not see returns the backend's `404` (existence-leak avoidance), which the page renders as not-found. This is VIEW only — no management controls.
- **Out of scope (non-goals):** any mutation/owner CRUD on stations, observations, or species (P2/P3); enrollment UI (P2); the account/admin areas (P2/P3); a station-coordinate map UI; and fixing the known backend gaps inherited from P0 (`GET /observation/` has no per-viewer visibility filtering; `classify-task` GETs have no auth).

## Capabilities

### New Capabilities
- `observation-browsing`: anonymous, server-rendered browsing of feeder observations — the landing recent-observations strip, the paginated feed with media thumbnails, and the shareable observation detail page (SSR with Open Graph/share meta, media via `/media/{object_name}`, species + station + confidence).
- `species-catalog`: anonymous, server-rendered browsing of the bird species catalog — the species list (over the `SpeciesMultiPublic` wrapper) and species detail.
- `station-management`: the **public VIEW** slice only in this phase — the optional-auth station list and station detail (owner sees private stations, anonymous sees public, hidden stations 404). Owner CRUD is added to this capability in P2.

### Modified Capabilities
- None.

## Impact

- **Frontend:** new routes under `frontend/src/routes/(public)/`: a rewritten `+page.svelte` (landing), `observations/+page.svelte` + `observations/+page.server.ts`, `observations/[id]/+page.svelte` + `observations/[id]/+page.server.ts` (with OG/share meta), `species/+page.svelte` + `species/+page.server.ts`, `species/[id]/+page.svelte` + `species/[id]/+page.server.ts`, `stations/+page.svelte` + `stations/+page.server.ts` (optional-auth), `stations/[id]/+page.svelte` + `stations/[id]/+page.server.ts`. Shared presentational components (observation card/thumbnail, pagination control) under `frontend/src/lib/components/`.
- **Backend:** none. All endpoints already exist and already serve the required (optional-)anonymous access (`backend/app/api/routes/{observations,species,stations}.py`). No model, route, or migration change.
- **Deploy:** none beyond P0 (no new services, ports, or Traefik config).
- **Settings:** none new. OG/share absolute URLs use the existing `PUBLIC_SITE_URL` introduced in P0.
- **Dependencies:** none new — built on the P0 SvelteKit/Tailwind/shadcn-svelte/openapi-fetch stack and the generated typed client.
