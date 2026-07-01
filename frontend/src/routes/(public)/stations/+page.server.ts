import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { DEFAULT_LIMIT, parsePage, skipFor } from '$lib/pagination';
import type { PageServerLoad } from './$types';

/**
 * Public station list with optional-authentication visibility. `serverApiClient`
 * forwards the session bearer ONLY when a `pp_session` cookie is present, so an
 * anonymous visitor sees only public stations while a logged-in owner also sees
 * their own private ones (the backend's optional-user filter decides). VIEW only.
 */
export const load: PageServerLoad = async ({ locals, url, fetch }) => {
	const limit = DEFAULT_LIMIT;
	const page = parsePage(url.searchParams);
	const skip = skipFor(page, limit);

	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/station/', {
			params: { query: { skip, limit } }
		})
	);
	if (!response.ok || !data) {
		error(502, 'Could not load stations');
	}

	return { items: data.data, count: data.count, page, limit };
};
