import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { DEFAULT_LIMIT, parsePage, skipFor } from '$lib/pagination';
import type { PageServerLoad } from './$types';

/**
 * Paginated observation feed. Derives `skip`/`limit` from the 1-based `?page`
 * query param and reads the `{data, count}` envelope from `GET /observation/`.
 * An out-of-range page returns an empty `data` array (not an error), which the
 * page renders as an empty slice with the next control disabled.
 */
export const load: PageServerLoad = async ({ locals, url, fetch }) => {
	const limit = DEFAULT_LIMIT;
	const page = parsePage(url.searchParams);
	const skip = skipFor(page, limit);

	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/observation/', {
			params: { query: { skip, limit } }
		})
	);
	if (!response.ok || !data) {
		error(502, 'Could not load observations');
	}

	return { items: data.data, count: data.count, page, limit };
};
