import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import type { PageServerLoad } from './$types';

/**
 * Species detail. A backend `404`/`422` (missing or invalid id) renders as a
 * not-found page. No auth required.
 */
export const load: PageServerLoad = async ({ locals, params, fetch }) => {
	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/species/{id}', {
			params: { path: { id: params.id } }
		})
	);
	if (response.status === 404 || response.status === 422) {
		error(404, 'Species not found');
	}
	if (!response.ok || !data) {
		error(502, 'Could not load species');
	}

	return { species: data };
};
