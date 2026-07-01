import { error } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { isOwnStation } from '$lib/stations';
import type { PageServerLoad } from './$types';

/**
 * The logged-in owner's own stations. `GET /station/` returns public stations
 * plus the caller's private ones (the bearer is forwarded); we keep only the
 * rows this user owns, since this is the management view — the public browse-all
 * lives under `(public)/stations`. Under the P0 `(app)` guard, so no auth check.
 */
export const load: PageServerLoad = async ({ locals, fetch }) => {
	const user = locals.user!;
	const client = serverApiClient(locals, fetch);
	// Owners have few stations; one page of the default backend limit is enough.
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/station/', { params: { query: { skip: 0, limit: 100 } } })
	);
	if (!response.ok || !data) {
		error(502, 'Could not load your stations');
	}

	const stations = data.data.filter((station) => isOwnStation(station, user.id));
	return { stations };
};
