import { error } from '@sveltejs/kit';
import { env } from '$env/dynamic/public';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { observationShareMeta } from '$lib/share';
import type { PageServerLoad } from './$types';

/**
 * Observation detail. Renders the `ObservationPublic` and pre-builds the Open
 * Graph / share metadata against the public base (`PUBLIC_SITE_URL`, or the
 * request origin in dev). A backend `404`/`422` (missing or invalid id) becomes
 * a SvelteKit not-found page rather than a server error.
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

	const base = env.PUBLIC_SITE_URL || url.origin;
	return { observation: data, meta: observationShareMeta(data, base) };
};
