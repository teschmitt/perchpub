import { fail } from '@sveltejs/kit';
import { serverApiClient } from '$lib/api/client';
import type { Actions, PageServerLoad } from './$types';

/** Read the parsed `{detail}` string from an openapi-fetch error body, if any. */
function detailOf(errorBody: unknown): string | undefined {
	const detail = (errorBody as { detail?: unknown } | undefined)?.detail;
	return typeof detail === 'string' ? detail : undefined;
}

interface OpsResult {
	message?: string;
	error?: string;
}

/**
 * Ops panel. Surfaces the backend health-check. Unlike the other loads this does
 * NOT bubble an unreachable backend to a 502 page — the whole point is to REPORT
 * reachability, so a transport failure is caught and shown as "unhealthy".
 */
export const load: PageServerLoad = async ({ locals, fetch }) => {
	const client = serverApiClient(locals, fetch);
	let healthy: boolean;
	try {
		const { data, response } = await client.GET('/api/v1/utils/health-check/');
		healthy = response.ok && data === true;
	} catch {
		healthy = false;
	}
	return { healthy };
};

export const actions = {
	// `POST /utils/test-email/` is superuser-guarded and functional only when the
	// backend's email settings are configured; we surface its response/error rather
	// than introducing config here.
	'test-email': async ({ request, locals, fetch }) => {
		const form = await request.formData();
		const email_to = String(form.get('email_to') ?? '').trim();
		if (!email_to) {
			const missing: OpsResult = { error: 'Enter an address to send the test email to.' };
			return fail(400, missing);
		}

		const client = serverApiClient(locals, fetch);
		const {
			data,
			error: errorBody,
			response
		} = await client.POST('/api/v1/utils/test-email/', {
			params: { query: { email_to } }
		});

		if (!response.ok) {
			const failed: OpsResult = {
				error: detailOf(errorBody) ?? 'Could not send the test email.'
			};
			return fail(response.status === 422 ? 422 : 502, failed);
		}

		const ok: OpsResult = { message: data?.message ?? 'Test email sent.' };
		return ok;
	}
} satisfies Actions;
