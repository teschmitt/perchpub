import { error, redirect, type Cookies } from '@sveltejs/kit';
import type { SessionUser } from '$lib/api/client';

/** Name of the BFF session cookie holding the backend JWT. */
export const SESSION_COOKIE = 'pp_session';

/**
 * Session lifetime in seconds — mirrors the backend's
 * `ACCESS_TOKEN_EXPIRE_MINUTES` (60 * 24 * 8 minutes = 8 days).
 */
export const SESSION_MAX_AGE = 60 * 60 * 24 * 8;

export interface SessionCookieOptions {
	httpOnly: true;
	secure: true;
	sameSite: 'lax';
	path: '/';
	maxAge: number;
}

/**
 * Cookie attributes for `pp_session`: `httpOnly` (client JS can't read the JWT),
 * `Secure`, `SameSite=Lax`, root path.
 */
export function sessionCookieOptions(maxAge: number): SessionCookieOptions {
	return { httpOnly: true, secure: true, sameSite: 'lax', path: '/', maxAge };
}

/**
 * Optional-auth helper: the session bearer, present only when a `pp_session`
 * cookie is set — so public pages stay anonymous-capable yet enrich for
 * logged-in owners.
 */
export function bearerFromCookies(cookies: Cookies): string | undefined {
	return cookies.get(SESSION_COOKIE) || undefined;
}

/**
 * `(app)`-zone guard. Returns the user, or redirects anonymous requests to the
 * login route carrying where they were headed (`?redirectTo=`).
 */
export function requireUser(user: SessionUser | null, pathname: string): SessionUser {
	if (!user) {
		redirect(303, `/login?redirectTo=${encodeURIComponent(pathname)}`);
	}
	return user;
}

/**
 * Superuser guard (used by P3 admin areas). Anonymous → login; a logged-in
 * non-superuser → `404` (so admin routes don't leak their existence). The
 * backend still `403`s the data as defense-in-depth.
 */
export function requireSuperuser(user: SessionUser | null, pathname: string): SessionUser {
	const current = requireUser(user, pathname);
	if (!current.is_superuser) {
		error(404, 'Not found');
	}
	return current;
}

/**
 * Validate a post-login `redirectTo` to a SAME-ORIGIN local path, defeating
 * open redirects (CWE-601): reject absolute URLs, protocol-relative `//host`,
 * and `/\`-backslash tricks. `redirectTo` is attacker-controllable, so anything
 * that isn't a single-leading-slash relative path falls back to `fallback`.
 */
export function safeRedirectTarget(
	raw: string | null | undefined,
	fallback = '/dashboard'
): string {
	if (!raw || raw[0] !== '/' || raw[1] === '/' || raw[1] === '\\') {
		return fallback;
	}
	return raw;
}
