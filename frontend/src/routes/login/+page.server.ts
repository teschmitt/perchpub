import { fail, redirect } from '@sveltejs/kit';
import { createApiClient, internalApiUrl } from '$lib/api/client';
import {
	SESSION_COOKIE,
	SESSION_MAX_AGE,
	safeRedirectTarget,
	sessionCookieOptions
} from '$lib/server/auth';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals, url }) => {
	// Already signed in → bounce to the post-login target.
	if (locals.user) {
		redirect(303, safeRedirectTarget(url.searchParams.get('redirectTo')));
	}
	return {};
};

export const actions: Actions = {
	default: async ({ request, cookies, fetch, url }) => {
		const form = await request.formData();
		const username = String(form.get('username') ?? '').trim();
		const password = String(form.get('password') ?? '');

		if (!username || !password) {
			return fail(400, { username, error: 'Email and password are required.' });
		}

		// OAuth2 password grant is form-encoded; serialize accordingly and let
		// the typed client validate the path/body against the generated schema.
		const client = createApiClient({ baseUrl: internalApiUrl(), fetch });
		const { data, response } = await client.POST('/api/v1/login/access-token', {
			body: { username, password, scope: '' },
			bodySerializer: (body) => new URLSearchParams(body as Record<string, string>).toString(),
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
		});

		if (!response.ok || !data?.access_token) {
			return fail(401, { username, error: 'Incorrect email or password.' });
		}

		// Set the httpOnly session cookie — the JWT never reaches client JS.
		cookies.set(SESSION_COOKIE, data.access_token, sessionCookieOptions(SESSION_MAX_AGE));
		redirect(303, safeRedirectTarget(url.searchParams.get('redirectTo')));
	}
};
