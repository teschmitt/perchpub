import { fail, redirect } from '@sveltejs/kit';
import { createApiClient, internalApiUrl } from '$lib/api/client';
import {
	SESSION_COOKIE,
	SESSION_MAX_AGE,
	secureCookies,
	sessionCookieOptions
} from '$lib/server/auth';
import type { Actions, PageServerLoad } from './$types';

interface SignupResult {
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
	default: async ({ request, cookies, fetch, url }) => {
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

		// Public signup: no bearer. The backend returns the SAME generic response
		// whether or not the email already exists (no account enumeration).
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

		// Immediately establish a session by performing the password grant with the
		// just-submitted credentials, then hand off into first-station setup. The
		// grant succeeds for a freshly-created account; it fails when the email
		// already belongs to an account whose password differs (signup was a no-op)
		// — in which case we fall back to the login form, asserting nothing about
		// whether the account existed (indistinguishable from a mistyped password).
		const grant = await client.POST('/api/v1/login/access-token', {
			body: { username: email, password, scope: '' },
			bodySerializer: (body) => new URLSearchParams(body as Record<string, string>).toString(),
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
		});

		if (!grant.response.ok || !grant.data?.access_token) {
			redirect(303, '/login');
		}

		// Set the httpOnly session cookie — the JWT never reaches client JS.
		// `Secure` follows the request scheme (see secureCookies) so it holds over
		// plain-HTTP dev — e.g. a phone at http://<lan-ip>:5173 — yet stays Secure
		// in prod behind Traefik.
		cookies.set(
			SESSION_COOKIE,
			grant.data.access_token,
			sessionCookieOptions(SESSION_MAX_AGE, secureCookies(url))
		);
		redirect(303, '/stations/new');
	}
} satisfies Actions;
