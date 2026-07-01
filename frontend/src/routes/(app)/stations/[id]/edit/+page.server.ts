import { error, fail, redirect } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { parseStationForm, type StationFieldErrors, type StationFormValues } from '$lib/stations';
import type { Actions, PageServerLoad } from './$types';

interface EditResult {
	forbidden?: boolean;
	notFound?: boolean;
	formError?: string;
	errors?: StationFieldErrors;
	values?: StationFormValues;
}

/**
 * Pre-fill the edit form from the loaded station. A backend `404` — the station
 * is unknown OR a private station the caller may not see (existence-leak
 * avoidance) — renders as not-found, leaking no detail. `422` (bad id) is the same.
 */
export const load: PageServerLoad = async ({ locals, params, fetch }) => {
	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/station/{id}', { params: { path: { id: params.id } } })
	);
	if (response.status === 404 || response.status === 422) {
		error(404, 'Station not found');
	}
	if (!response.ok || !data) {
		error(502, 'Could not load the station');
	}
	return { station: data };
};

export const actions = {
	// `StationUpdate` extends `StationBase` with no overrides — latitude/longitude
	// are required, so the form resubmits the COMPLETE body, not a partial patch.
	default: async ({ request, locals, params, fetch }) => {
		const form = await request.formData();
		const values: StationFormValues = {
			latitude: String(form.get('latitude') ?? ''),
			longitude: String(form.get('longitude') ?? ''),
			is_private: form.get('is_private') != null
		};

		const parsed = parseStationForm(form);
		if (!parsed.ok) {
			const invalid: EditResult = { errors: parsed.errors, values };
			return fail(400, invalid);
		}

		const client = serverApiClient(locals, fetch);
		const { response } = await client.PUT('/api/v1/station/{id}', {
			params: { path: { id: params.id } },
			body: parsed.value
		});

		// The backend enforces ownership per row: 403 on a foreign PUBLIC station,
		// 404 on a foreign PRIVATE one (or unknown id). Reflect each without saving.
		if (response.status === 403) {
			const forbidden: EditResult = { forbidden: true };
			return fail(403, forbidden);
		}
		if (response.status === 404) {
			const notFound: EditResult = { notFound: true };
			return fail(404, notFound);
		}
		if (!response.ok) {
			const upstream: EditResult = {
				formError: 'Could not save the station. Please check the values and try again.',
				values
			};
			return fail(response.status === 422 ? 422 : 502, upstream);
		}

		redirect(303, '/stations/mine');
	}
} satisfies Actions;
