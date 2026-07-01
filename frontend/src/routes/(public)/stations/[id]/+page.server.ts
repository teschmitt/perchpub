import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import type { PageServerLoad } from './$types';

/**
 * Public station detail with optional-authentication visibility. A backend `404`
 * — whether the station does not exist OR is a private station the caller may
 * not see (existence-leak avoidance) — renders as a not-found page rather than
 * disclosing the station. A `422` (invalid id) is treated the same. VIEW only.
 */
export const load: PageServerLoad = async ({ locals, params, fetch }) => {
	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/station/{id}', {
			params: { path: { id: params.id } }
		})
	);
	if (response.status === 404 || response.status === 422) {
		error(404, 'Station not found');
	}
	if (!response.ok || !data) {
		error(502, 'Could not load station');
	}

	return { station: data };
};
