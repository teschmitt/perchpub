import { fail, redirect } from '@sveltejs/kit';
import { serverApiClient } from '$lib/api/client';
import { parseStationForm, type StationFieldErrors, type StationFormValues } from '$lib/stations';
import type { Actions } from './$types';

interface CreateResult {
	errors?: StationFieldErrors;
	formError?: string;
	values: StationFormValues;
}

export const actions = {
	// Map picker deferred (see proposal non-goals): coordinates are entered as
	// plain numeric latitude/longitude inputs, validated against StationBase's ranges.
	default: async ({ request, locals, fetch }) => {
		const form = await request.formData();
		const values: StationFormValues = {
			latitude: String(form.get('latitude') ?? ''),
			longitude: String(form.get('longitude') ?? ''),
			is_private: form.get('is_private') != null
		};

		const parsed = parseStationForm(form);
		if (!parsed.ok) {
			const invalid: CreateResult = { errors: parsed.errors, values };
			return fail(400, invalid);
		}

		// owner_id is set server-side from the bearer; the browser never supplies it.
		const client = serverApiClient(locals, fetch);
		const { response } = await client.POST('/api/v1/station/', { body: parsed.value });

		if (!response.ok) {
			const upstream: CreateResult = {
				formError: 'Could not create the station. Please check the values and try again.',
				values
			};
			return fail(response.status === 422 ? 422 : 502, upstream);
		}

		redirect(303, '/stations/mine');
	}
} satisfies Actions;
