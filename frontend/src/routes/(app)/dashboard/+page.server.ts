import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { isOwnStation } from '$lib/stations';
import type { PageServerLoad } from './$types';

/**
 * Onboarding-aware dashboard: count how many stations the current user owns so
 * the page can lead with a "set up your first station" call to action until at
 * least one exists. Reuses the same `GET /station/` + `isOwnStation` filter as
 * `/stations/mine` (owners have few stations; one page of the default limit is
 * enough). Under the P0 `(app)` guard, so no auth check here.
 */
export const load: PageServerLoad = async ({ locals, fetch }) => {
	const user = locals.user!;
	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/station/', { params: { query: { skip: 0, limit: 100 } } })
	);
	if (!response.ok || !data) {
		error(502, 'Could not load your dashboard');
	}

	const stationCount = data.data.filter((station) => isOwnStation(station, user.id)).length;
	return { stationCount };
};
