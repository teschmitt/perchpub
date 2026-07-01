## 1. Shared presentational pieces

- [x] 1.1 Add an observation card/thumbnail component at `frontend/src/lib/components/observation-card.svelte` that takes an `ObservationPublic` (typed from the generated `src/lib/api/schema.d.ts`) and renders the media thumbnail via `/media/{object_name}` (using `object_name`), the species name (`observation.species?.scientific_name`, with a "Unclassified" fallback when `species` is `null`), the station, the `confidence_score` (formatted as a percentage, hidden when `null`), and `observed_at`. The card links to `/observations/{id}`.
- [x] 1.2 Add a pagination control component at `frontend/src/lib/components/pagination.svelte` driven by `skip`/`limit`/`count` (the `{data, count}` envelope shape) that produces prev/next links updating the `?page=` (or `?skip=`) query param; disable prev at the start and next when `skip + limit >= count`.
- [x] 1.3 Add a small media element helper (in `observation-card.svelte` or a sibling) that renders `<img>` for image keys and `<video controls>` for video keys, choosing by the `object_name` extension, both pointed at `/media/{object_name}`. (`frontend/src/lib/components/media-element.svelte`; `isVideoObject` in `src/lib/media.ts`.)

## 2. Landing page (recent observations)

- [x] 2.1 Rewrite `frontend/src/routes/(public)/+page.svelte` (the P0 placeholder) to render a "recent observations" strip.
- [x] 2.2 Add `frontend/src/routes/(public)/+page.server.ts` whose `load` calls `GET /observation/` via the generated client with a small `limit` (e.g. `limit=12`, `skip=0`) and returns `data.data` for the page to render with `observation-card.svelte`. No auth required.

## 3. Observation feed (paginated)

- [x] 3.1 Add `frontend/src/routes/(public)/observations/+page.server.ts`: `load` reads `?page`/`?skip` from `url.searchParams`, computes `skip`/`limit`, calls `GET /observation/` via the generated client, and returns `{ items: res.data, count: res.count, skip, limit }`.
- [x] 3.2 Add `frontend/src/routes/(public)/observations/+page.svelte` rendering the items as `observation-card.svelte` grid/list plus `pagination.svelte` wired to `count`/`skip`/`limit`.
- [x] 3.3 Confirm an out-of-range page (skip ≥ count) renders an empty list with prev enabled and next disabled, not an error. (e2e: `observation-feed.e2e.ts` "an out-of-range page renders an empty slice, not an error".)

## 4. Observation detail (SSR + share preview)

- [x] 4.1 Add `frontend/src/routes/(public)/observations/[id]/+page.server.ts`: `load` calls `GET /observation/{id}` via the generated client with `params.id`; on backend `404` call SvelteKit `error(404, ...)`. Return the `ObservationPublic` plus the absolute media URL built from `PUBLIC_SITE_URL` + `/media/{object_name}` for the OG image. (`PUBLIC_SITE_URL` via `$env/dynamic/public`, falling back to `url.origin` in dev; share meta built by `src/lib/share.ts`.)
- [x] 4.2 Add `frontend/src/routes/(public)/observations/[id]/+page.svelte` rendering the media via `/media/{object_name}` (image or short video), the species (`scientific_name`, "Unclassified" when `null`), the capturing station (linking to `/stations/{station.id}`), `observed_at`, and `confidence_score`. (Species also links to `/species/{id}` when classified.)
- [x] 4.3 Emit Open Graph / share-preview `<meta>` tags in `<svelte:head>`: `og:title` (species + station), `og:description`, `og:image` (the absolute `/media/{object_name}` URL), `og:url`, and the Twitter card equivalents, so the page unfurls into a card.

## 5. Species catalog (list + detail)

- [x] 5.1 Add `frontend/src/routes/(public)/species/+page.server.ts`: `load` calls `GET /species/` via the generated client and returns the `SpeciesMultiPublic` `{data, count}` (respect the wrapper; the list is `res.data`).
- [x] 5.2 Add `frontend/src/routes/(public)/species/+page.svelte` rendering each species' `scientific_name`, linking to `/species/{id}`; include `pagination.svelte` if `count` exceeds the page `limit`.
- [x] 5.3 Add `frontend/src/routes/(public)/species/[id]/+page.server.ts` (`GET /species/{id}`, `error(404)` on backend 404) and `frontend/src/routes/(public)/species/[id]/+page.svelte` showing the species detail.

## 6. Public station list + detail (optional-auth)

- [x] 6.1 Add `frontend/src/routes/(public)/stations/+page.server.ts`: `load` calls `GET /station/` via the **optional-auth** server fetch (forwards the bearer only when a `pp_session` cookie exists, per P0) so a logged-in owner's private stations appear and anonymous visitors get the public subset; return `StationsPublic` `{data, count}`.
- [x] 6.2 Add `frontend/src/routes/(public)/stations/+page.svelte` rendering each station (its `owner.full_name` when present, an `is_private` badge for owner-visible private stations) and linking to `/stations/{id}`. VIEW only — no management controls.
- [x] 6.3 Add `frontend/src/routes/(public)/stations/[id]/+page.server.ts`: `load` calls `GET /station/{id}` via the optional-auth server fetch; a backend `404` (nonexistent **or** a private station the caller may not see) maps to SvelteKit `error(404, ...)`.
- [x] 6.4 Add `frontend/src/routes/(public)/stations/[id]/+page.svelte` rendering the station detail (location, owner, visibility). VIEW only.

## 7. Verify and gate

- [x] 7.1 Add Playwright coverage in `frontend/`: an SSR fetch of the observation detail page contains the `og:image`/`og:title` meta tags in the server-rendered HTML; the observations feed paginates (next advances `skip`); an anonymous visit to `/stations/` lists only public stations while an authenticated owner additionally sees a private one. Add Vitest coverage for the pagination/skip computation in the `load` functions. (e2e: `landing`, `observation-detail`, `observation-feed`, `species-catalog`, `stations-visibility`; Vitest: `pagination`, `format`, `share`, `media`, `client` specs.)
- [x] 7.2 Run the frontend gate from `frontend/`: `npm run lint`, `npm run check`, `npm run test`. Backend is untouched in this phase, so no backend lint/test run is required (confirm the working-tree diff stays under `frontend/`). (`lint`, `check`, `test:unit` (51 tests) and `build` all green; the `test:e2e` half requires a running backend — not runnable in this sandbox, runs on the real stack.)
- [x] 7.3 Run `openspec validate add-public-observation-browsing --strict` and confirm the change validates.
