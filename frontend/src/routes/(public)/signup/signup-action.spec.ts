import { type ActionFailure, isRedirect } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { actions, load } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

const GENERIC = "If this email is new, you'll receive a confirmation email.";

interface SignupData {
	success?: boolean;
	message?: string;
	error?: string;
	values?: { email?: string; full_name?: string };
}

describe('signup register action', () => {
	it('POSTs to /users/signup and relays the generic confirmation message', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { message: GENERIC })
		);
		const result = (await actions.default(
			fakeActionEvent({
				form: { email: 'new@example.com', password: 'password123', full_name: 'New Person' },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.default>[0]
		)) as SignupData;

		const req = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(req.method).toBe('POST');
		expect(req.url).toBe('http://localhost:8000/api/v1/users/signup');
		await expect(req.json()).resolves.toMatchObject({
			email: 'new@example.com',
			password: 'password123'
		});
		expect(result).toMatchObject({ success: true, message: GENERIC });
	});

	it('shows the same generic message for an already-taken email (no enumeration)', async () => {
		// The backend returns the identical generic body whether or not the email
		// existed; the action relays it verbatim and never branches on existence.
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { message: GENERIC })
		);
		const result = (await actions.default(
			fakeActionEvent({
				form: { email: 'taken@example.com', password: 'password123' },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.default>[0]
		)) as SignupData;
		expect(result).toMatchObject({ success: true, message: GENERIC });
	});

	it('requires an email and password before calling the backend', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () => jsonResponse(200));
		const failure = (await actions.default(
			fakeActionEvent({
				form: { email: '', password: '' },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.default>[0]
		)) as ActionFailure<SignupData>;
		expect(fetchMock).not.toHaveBeenCalled();
		expect(failure.status).toBe(400);
		expect(failure.data.error).toBeTruthy();
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
