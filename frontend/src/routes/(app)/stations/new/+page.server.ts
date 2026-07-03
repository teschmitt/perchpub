import { fail } from '@sveltejs/kit';
import { serverApiClient } from '$lib/api/client';
import type { EnrollResult } from '$lib/enrollment';
import { findNewStationId } from '$lib/enrollment';
import { isOwnStation, parseStationForm } from '$lib/stations';
import type { Actions } from './$types';

/** The operator's current station ids (used as the enrollment baseline). */
async function ownedStationIds(
	locals: App.Locals,
	fetch: typeof globalThis.fetch
): Promise<string[]> {
	const client = serverApiClient(locals, fetch);
	const { data } = await client.GET('/api/v1/station/', {
		params: { query: { skip: 0, limit: 100 } }
	});
	const userId = locals.user!.id;
	return (data?.data ?? []).filter((s) => isOwnStation(s, userId)).map((s) => s.id);
}

export const actions = {
	// Start an enrollment session. The device-side confirm step is out of browser
	// scope (the Pi performs POST /enrollment/confirm/{session_id}).
	create: async ({ request, locals, fetch, setHeaders }) => {
		// The response carries the one-time auth_token — never let it be cached
		// (spec: the credential SHALL be served no-store).
		setHeaders({ 'cache-control': 'no-store' });
		const form = await request.formData();
		const values = {
			latitude: String(form.get('latitude') ?? ''),
			longitude: String(form.get('longitude') ?? ''),
			is_private: form.get('is_private') != null
		};

		const parsed = parseStationForm(form);
		if (!parsed.ok) {
			const invalid: EnrollResult = { intent: 'create', errors: parsed.errors, values };
			return fail(400, invalid);
		}

		const client = serverApiClient(locals, fetch);
		const { data, response } = await client.POST('/api/v1/enrollment/create', {
			body: {
				latitude: parsed.value.latitude,
				longitude: parsed.value.longitude,
				is_private: parsed.value.is_private
			}
		});

		if (!response.ok || !data) {
			const upstream: EnrollResult = {
				intent: 'create',
				formError: 'Could not start enrollment. Please try again.',
				values
			};
			return fail(response.status === 422 ? 422 : 502, upstream);
		}

		// Capture the baseline AFTER the session is created; the new station only
		// appears once the device confirms, so it cannot be in this set.
		const baseline = await ownedStationIds(locals, fetch);
		const result: EnrollResult = {
			intent: 'create',
			session: {
				session_id: data.session_id,
				auth_token: data.auth_token,
				ca_pin: data.ca_pin,
				expires_at: data.expires_at
			},
			baseline
		};
		return result;
	},

	// No operator poll endpoint exists — confirm by diffing the station list
	// against the baseline captured at session start.
	check: async ({ request, locals, fetch, setHeaders }) => {
		// The enroll page re-renders its credential panel on this response too.
		setHeaders({ 'cache-control': 'no-store' });
		const form = await request.formData();
		let baseline: string[] = [];
		try {
			const parsed = JSON.parse(String(form.get('baseline') ?? '[]'));
			if (Array.isArray(parsed)) {
				baseline = parsed.filter((v): v is string => typeof v === 'string');
			}
		} catch {
			baseline = [];
		}

		const client = serverApiClient(locals, fetch);
		const { data, response } = await client.GET('/api/v1/station/', {
			params: { query: { skip: 0, limit: 100 } }
		});
		if (!response.ok || !data) {
			const upstream: EnrollResult = {
				intent: 'check',
				formError: 'Could not check for the new station. Please try again.'
			};
			return fail(502, upstream);
		}

		const newStationId = findNewStationId(baseline, data.data, locals.user!.id);
		const result: EnrollResult = { intent: 'check', newStationId };
		return result;
	}
} satisfies Actions;
