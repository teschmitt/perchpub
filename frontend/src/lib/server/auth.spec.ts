import { isHttpError, isRedirect } from '@sveltejs/kit';
import { describe, expect, it } from 'vitest';
import type { SessionUser } from '$lib/api/client';
import {
	SESSION_COOKIE,
	bearerFromCookies,
	requireSuperuser,
	requireUser,
	safeRedirectTarget,
	sessionCookieOptions
} from './auth';

const user: SessionUser = {
	id: '00000000-0000-0000-0000-000000000001',
	email: 'owner@example.com',
	is_active: true,
	is_superuser: false,
	full_name: null
};
const superuser: SessionUser = { ...user, is_superuser: true };

function fakeCookies(value?: string) {
	return {
		get: (name: string) => (name === SESSION_COOKIE ? value : undefined)
	} as unknown as import('@sveltejs/kit').Cookies;
}

describe('bearerFromCookies', () => {
	it('returns the token when the session cookie is present', () => {
		expect(bearerFromCookies(fakeCookies('jwt123'))).toBe('jwt123');
	});

	it('returns undefined when no session cookie is present', () => {
		expect(bearerFromCookies(fakeCookies(undefined))).toBeUndefined();
	});
});

describe('sessionCookieOptions', () => {
	it('is httpOnly, secure, lax, root-path with the given maxAge', () => {
		expect(sessionCookieOptions(123)).toEqual({
			httpOnly: true,
			secure: true,
			sameSite: 'lax',
			path: '/',
			maxAge: 123
		});
	});
});

describe('requireUser', () => {
	it('returns the user when present', () => {
		expect(requireUser(user, '/dashboard')).toBe(user);
	});

	it('redirects to /login carrying the redirectTo when anonymous', () => {
		try {
			requireUser(null, '/dashboard');
			expect.unreachable('requireUser should redirect anonymous requests');
		} catch (e) {
			expect(isRedirect(e)).toBe(true);
			expect((e as { status: number }).status).toBe(303);
			expect((e as { location: string }).location).toBe('/login?redirectTo=%2Fdashboard');
		}
	});
});

describe('requireSuperuser', () => {
	it('returns the user when superuser', () => {
		expect(requireSuperuser(superuser, '/admin')).toBe(superuser);
	});

	it('404s a logged-in non-superuser (does not leak existence)', () => {
		try {
			requireSuperuser(user, '/admin');
			expect.unreachable('requireSuperuser should 404 a non-superuser');
		} catch (e) {
			expect(isHttpError(e)).toBe(true);
			expect((e as { status: number }).status).toBe(404);
		}
	});

	it('redirects an anonymous request to login', () => {
		try {
			requireSuperuser(null, '/admin');
			expect.unreachable('requireSuperuser should redirect anonymous requests');
		} catch (e) {
			expect(isRedirect(e)).toBe(true);
			expect((e as { status: number }).status).toBe(303);
		}
	});
});

describe('safeRedirectTarget', () => {
	it('accepts a same-origin single-leading-slash path', () => {
		expect(safeRedirectTarget('/dashboard')).toBe('/dashboard');
		expect(safeRedirectTarget('/stations/123')).toBe('/stations/123');
	});

	it('falls back for an absolute URL (open-redirect)', () => {
		expect(safeRedirectTarget('https://evil.example')).toBe('/dashboard');
	});

	it('falls back for a protocol-relative //host', () => {
		expect(safeRedirectTarget('//evil.example')).toBe('/dashboard');
	});

	it('falls back for a backslash trick', () => {
		expect(safeRedirectTarget('/\\evil.example')).toBe('/dashboard');
	});

	it('falls back for null or empty', () => {
		expect(safeRedirectTarget(null)).toBe('/dashboard');
		expect(safeRedirectTarget('')).toBe('/dashboard');
	});

	it('honours a custom fallback', () => {
		expect(safeRedirectTarget(null, '/')).toBe('/');
	});
});
