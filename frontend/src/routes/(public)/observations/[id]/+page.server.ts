import { error, fail } from '@sveltejs/kit';
import { env } from '$env/dynamic/public';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { latestClassifyStatus } from '$lib/classify';
import { observationShareMeta } from '$lib/share';
import type { components } from '$lib/api/schema';
import type { Actions, PageServerLoad } from './$types';

type SpeciesPublic = components['schemas']['SpeciesPublic'];

// A high cap so the reclassify <select> lists the whole (small) catalogue.
const SPECIES_LIMIT = 1000;

/** Read the parsed `{detail}` string from an openapi-fetch error body, if any. */
function detailOf(errorBody: unknown): string | undefined {
	const detail = (errorBody as { detail?: unknown } | undefined)?.detail;
	return typeof detail === 'string' ? detail : undefined;
}

interface ReclassifyResult {
	reclassified?: boolean;
	reclassifyError?: string;
}

/**
 * Observation detail. Renders the `ObservationPublic` + Open Graph share metadata
 * and adds two P3 surfaces:
 *  - `latestStatus`: the most-recent classify task's status for the inline badge,
 *    from `GET /classify-task/?observation={id}` (public — the GET carries no
 *    backend auth; `latestClassifyStatus` picks `data[0]`, the newest).
 *  - `species`: the catalogue for the superuser-only reclassification <select>,
 *    fetched ONLY for a superuser (anonymous/owner visitors never hit `/species/`).
 * A backend `404`/`422` on the observation becomes a not-found page.
 */
export const load: PageServerLoad = async ({ locals, params, url, fetch }) => {
	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/observation/{id}', {
			params: { path: { id: params.id } }
		})
	);
	if (response.status === 404 || response.status === 422) {
		error(404, 'Observation not found');
	}
	if (!response.ok || !data) {
		error(502, 'Could not load observation');
	}

	const { data: tasks } = await requestUpstream(
		client.GET('/api/v1/classify-task/', {
			params: { query: { observation: params.id, limit: 1 } }
		})
	);
	const latestStatus = latestClassifyStatus(tasks?.data ?? []);

	let species: SpeciesPublic[] = [];
	if (locals.user?.is_superuser) {
		const { data: speciesData } = await requestUpstream(
			client.GET('/api/v1/species/', { params: { query: { limit: SPECIES_LIMIT } } })
		);
		species = speciesData?.data ?? [];
	}

	const base = env.PUBLIC_SITE_URL || url.origin;
	return { observation: data, meta: observationShareMeta(data, base), latestStatus, species };
};

export const actions = {
	// Superuser manual reclassification. `ObservationUpdate` inherits `confidence_score`
	// + `classification_result` as REQUIRED, so we re-read the observation and carry
	// both over UNCHANGED (a `{species_id, manually_classified}`-only body 422s). The
	// backend `get_current_active_superuser` guard on `PUT /observation/{id}` is the
	// defense-in-depth; a non-superuser who reaches here gets the backend 403 surfaced.
	reclassify: async ({ request, locals, params, fetch }) => {
		const form = await request.formData();
		const species_id = String(form.get('species_id') ?? '').trim();
		if (!species_id) {
			const missing: ReclassifyResult = { reclassifyError: 'Choose a species to assign.' };
			return fail(400, missing);
		}

		const client = serverApiClient(locals, fetch);
		const current = await requestUpstream(
			client.GET('/api/v1/observation/{id}', { params: { path: { id: params.id } } })
		);
		if (current.response.status === 404 || current.response.status === 422) {
			const gone: ReclassifyResult = { reclassifyError: 'This observation no longer exists.' };
			return fail(404, gone);
		}
		if (!current.response.ok || !current.data) {
			const upstream: ReclassifyResult = {
				reclassifyError: 'Could not load the observation to reclassify.'
			};
			return fail(502, upstream);
		}

		const { error: errorBody, response } = await client.PUT('/api/v1/observation/{id}', {
			params: { path: { id: params.id } },
			body: {
				species_id,
				manually_classified: true,
				confidence_score: current.data.confidence_score,
				classification_result: current.data.classification_result
			}
		});

		if (response.status === 403) {
			const forbidden: ReclassifyResult = {
				reclassifyError: detailOf(errorBody) ?? 'You do not have permission to reclassify.'
			};
			return fail(403, forbidden);
		}
		if (!response.ok) {
			const upstream: ReclassifyResult = {
				reclassifyError: 'Could not reclassify the observation. Please try again.'
			};
			return fail(response.status === 422 ? 422 : 502, upstream);
		}

		// ObservationPublic exposes no `manually_classified`, so a reload cannot show
		// that flag; the success signal for the indicator is this action result. The
		// re-run load DOES reflect the new species on `data.observation`.
		const done: ReclassifyResult = { reclassified: true };
		return done;
	}
} satisfies Actions;
