import { fail, redirect } from '@sveltejs/kit';
import { createApiClient, internalApiUrl } from '$lib/api/client';
import type { Actions, PageServerLoad } from './$types';

interface SignupResult {
	success?: boolean;
	message?: string;
	error?: string;
	values?: { email?: string; full_name?: string };
}

export const load: PageServerLoad = async ({ locals }) => {
	// Public zone, no guard — but a logged-in user has no business here.
	if (locals.user) {
		redirect(303, '/dashboard');
	}
	return {};
};

export const actions = {
	default: async ({ request, fetch }) => {
		const form = await request.formData();
		const email = String(form.get('email') ?? '').trim();
		const password = String(form.get('password') ?? '');
		const full_name = String(form.get('full_name') ?? '').trim();

		if (!email || !password) {
			return fail(400, {
				error: 'Email and password are required.',
				values: { email, full_name }
			} satisfies SignupResult);
		}

		// Public signup: no bearer. The backend returns the SAME generic message
		// whether or not the email already exists (no account enumeration), so the
		// action relays it verbatim and never asserts an account was created.
		const client = createApiClient({ baseUrl: internalApiUrl(), fetch });
		const { data, response } = await client.POST('/api/v1/users/signup', {
			body: { email, password, full_name: full_name || null }
		});

		if (!response.ok || !data) {
			return fail(response.status === 422 ? 422 : 502, {
				error: 'Could not complete signup. Check your email and password and try again.',
				values: { email, full_name }
			} satisfies SignupResult);
		}

		return { success: true, message: data.message } satisfies SignupResult;
	}
} satisfies Actions;
