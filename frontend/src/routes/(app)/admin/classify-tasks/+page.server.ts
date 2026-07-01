import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { isClassifyStatus } from '$lib/classify';
import { DEFAULT_LIMIT, parsePage, skipFor } from '$lib/pagination';
import type { PageServerLoad } from './$types';

/**
 * Superuser classify-task list. Read-only.
 *
 * NOTE: `GET /classify-task/` and `GET /classify-task/{id}` carry NO backend
 * authorization dependency (a known backend gap, flagged in P0's design and out
 * of scope here). This surface is therefore gated ONLY by the `(app)/admin`
 * client-side superuser guard and offers no mutation of classify tasks.
 */
export const load: PageServerLoad = async ({ locals, url, fetch }) => {
	const limit = DEFAULT_LIMIT;
	const page = parsePage(url.searchParams);
	const skip = skipFor(page, limit);

	// Only the two filters the endpoint accepts; an invalid status is dropped.
	const rawStatus = url.searchParams.get('status');
	const statusFilter = isClassifyStatus(rawStatus) ? rawStatus : null;
	const observationFilter = url.searchParams.get('observation')?.trim() || null;

	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/classify-task/', {
			params: {
				query: {
					skip,
					limit,
					...(statusFilter ? { status: statusFilter } : {}),
					...(observationFilter ? { observation: observationFilter } : {})
				}
			}
		})
	);
	if (!response.ok || !data) {
		error(502, 'Could not load classify tasks');
	}

	return {
		items: data.data,
		count: data.count,
		page,
		limit,
		statusFilter,
		observationFilter
	};
};
