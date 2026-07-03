import { type ActionFailure, isRedirect } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { actions, load } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

const GENERIC = "If this email is new, you'll receive a confirmation email.";

interface SignupData {
	error?: string;
	values?: { email?: string; full_name?: string };
}

async function runDefault(event: Parameters<typeof actions.default>[0]) {
	try {
		return { failure: (await actions.default(event)) as ActionFailure<SignupData> };
	} catch (e) {
		if (isRedirect(e)) {
			return { redirect: { status: e.status, location: e.location } };
		}
		throw e;
	}
}

describe('signup register action', () => {
	it('signs the new account in and sends it to first-station setup', async () => {
		const cookieSet = vi.fn();
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async (req) => {
			if (req.url.endsWith('/api/v1/users/signup')) {
				return jsonResponse(200, { message: GENERIC });
			}
			if (req.url.endsWith('/api/v1/login/access-token')) {
				return jsonResponse(200, { access_token: 'fresh-jwt', token_type: 'bearer' });
			}
			return jsonResponse(500);
		});

		const result = await runDefault(
			fakeActionEvent({
				form: { email: 'new@example.com', password: 'password123', full_name: 'New Person' },
				fetch: fetchMock as unknown as typeof fetch,
				cookies: { set: cookieSet }
			}) as Parameters<typeof actions.default>[0]
		);

		// The account is created, then the password grant is performed with the
		// just-submitted credentials.
		const grantReq = fetchMock.mock.calls.find((c) =>
			(c[0] as unknown as Request).url.endsWith('/api/v1/login/access-token')
		)![0] as unknown as Request;
		expect(grantReq.method).toBe('POST');

		// The BFF session cookie is set with the granted JWT, and the user is
		// handed off into first-station setup.
		expect(cookieSet).toHaveBeenCalledWith(
			'pp_session',
			'fresh-jwt',
			expect.objectContaining({ httpOnly: true, path: '/' })
		);
		expect(result.redirect).toEqual({ status: 303, location: '/stations/new' });
	});

	it('falls back to the login form (no session) when the follow-up grant fails', async () => {
		// An already-registered email makes /users/signup a no-op that still returns
		// the SAME generic body; the tell is the grant failing on the wrong password.
		// Indistinguishable from a mistyped password — reveals nothing about existence.
		const cookieSet = vi.fn();
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async (req) => {
			if (req.url.endsWith('/api/v1/users/signup')) {
				return jsonResponse(200, { message: GENERIC });
			}
			if (req.url.endsWith('/api/v1/login/access-token')) {
				return jsonResponse(401, { detail: 'Incorrect email or password' });
			}
			return jsonResponse(500);
		});

		const result = await runDefault(
			fakeActionEvent({
				form: { email: 'taken@example.com', password: 'wrong-password' },
				fetch: fetchMock as unknown as typeof fetch,
				cookies: { set: cookieSet }
			}) as Parameters<typeof actions.default>[0]
		);

		expect(cookieSet).not.toHaveBeenCalled();
		expect(result.redirect).toEqual({ status: 303, location: '/login' });
	});

	it('requires an email and password before calling the backend', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () => jsonResponse(200));
		const result = await runDefault(
			fakeActionEvent({
				form: { email: '', password: '' },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.default>[0]
		);
		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.failure?.status).toBe(400);
		expect(result.failure?.data.error).toBeTruthy();
	});

	it('re-renders a form error (no session) when the signup call itself fails', async () => {
		const cookieSet = vi.fn();
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(422, { detail: [{ msg: 'bad', loc: ['body', 'password'] }] })
		);
		const result = await runDefault(
			fakeActionEvent({
				form: { email: 'x@example.com', password: 'short' },
				fetch: fetchMock as unknown as typeof fetch,
				cookies: { set: cookieSet }
			}) as Parameters<typeof actions.default>[0]
		);
		expect(cookieSet).not.toHaveBeenCalled();
		expect(result.failure?.status).toBe(422);
		expect(result.failure?.data.error).toBeTruthy();
	});
});

describe('signup load', () => {
	it('redirects an already-logged-in visitor away from signup', async () => {
		let redirected: { status: number; location: string } | undefined;
		try {
			await load({
				locals: { session: 'jwt', user: fakeUser() },
				url: new URL('http://localhost/signup')
			} as unknown as Parameters<typeof load>[0]);
		} catch (e) {
			if (isRedirect(e)) {
				redirected = { status: e.status, location: e.location };
			} else {
				throw e;
			}
		}
		expect(redirected?.status).toBe(303);
		expect(redirected?.location).toBe('/dashboard');
	});

	it('lets an anonymous visitor through', async () => {
		const result = await load({
			locals: { session: null, user: null },
			url: new URL('http://localhost/signup')
		} as unknown as Parameters<typeof load>[0]);
		expect(result).toEqual({});
	});
});
