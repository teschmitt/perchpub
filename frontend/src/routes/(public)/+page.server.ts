import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import type { PageServerLoad } from './$types';

/** How many recent observations the landing strip shows. */
const RECENT_LIMIT = 12;

/**
 * Landing page data: a bounded, server-rendered slice of the most recent
 * observations. No auth required — `serverApiClient` forwards a bearer only when
 * a session cookie is present, so anonymous visitors get the public response.
 */
export const load: PageServerLoad = async ({ locals, fetch }) => {
	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/observation/', {
			params: { query: { skip: 0, limit: RECENT_LIMIT } }
		})
	);
	if (!response.ok || !data) {
		error(502, 'Could not load recent observations');
	}
	return { observations: data.data };
};
