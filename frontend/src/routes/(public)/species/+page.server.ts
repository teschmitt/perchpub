import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { DEFAULT_LIMIT, parsePage, skipFor } from '$lib/pagination';
import type { PageServerLoad } from './$types';

/**
 * Species catalog list. Reads the `SpeciesMultiPublic` `{data, count}` wrapper
 * from `GET /species/`, paginating over `skip`/`limit`. No auth required.
 */
export const load: PageServerLoad = async ({ locals, url, fetch }) => {
	const limit = DEFAULT_LIMIT;
	const page = parsePage(url.searchParams);
	const skip = skipFor(page, limit);

	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/species/', {
			params: { query: { skip, limit } }
		})
	);
	if (!response.ok || !data) {
		error(502, 'Could not load species catalog');
	}

	return { items: data.data, count: data.count, page, limit };
};
