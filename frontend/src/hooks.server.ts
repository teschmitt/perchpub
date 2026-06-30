import type { Handle } from '@sveltejs/kit';
import { createApiClient, internalApiUrl } from '$lib/api/client';
import { SESSION_COOKIE } from '$lib/server/auth';
import { type ResolvedSession, resolveSession } from '$lib/server/session';

/**
 * BFF session handle. Reads the `pp_session` cookie, forwards the JWT to the
 * backend as a `Bearer` to resolve the current user (`/users/me`) once per
 * request, and exposes the result on `event.locals`. A backend `401` (expired /
 * invalid token) clears the cookie. The JWT is never exposed to the browser.
 */
export const handle: Handle = async ({ event, resolve }) => {
	const token = event.cookies.get(SESSION_COOKIE) || undefined;

	let resolved: ResolvedSession;
	try {
		resolved = await resolveSession(token, async (jwt) => {
			const client = createApiClient({
				baseUrl: internalApiUrl(),
				bearer: jwt,
				fetch: event.fetch
			});
			const { data, response } = await client.GET('/api/v1/users/me');
			return { status: response.status, user: data ?? null };
		});
	} catch {
		// Backend unreachable (network error, not a 401): degrade to anonymous
		// for this request WITHOUT clearing the cookie (transient — only a real
		// 401 clears it). Public pages stay reachable; the (app) guard still
		// redirects since locals.user is null.
		resolved = { session: null, user: null, clearCookie: false };
	}

	const { session, user, clearCookie } = resolved;

	if (clearCookie) {
		event.cookies.delete(SESSION_COOKIE, { path: '/' });
	}
	event.locals.session = session;
	event.locals.user = user;

	return resolve(event);
};
