import { type ActionFailure, isRedirect } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { actions } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

interface AccountData {
	intent?: string;
	success?: boolean;
	error?: string;
	fieldErrors?: {
		full_name?: string;
		email?: string;
		current_password?: string;
		new_password?: string;
	};
	values?: { full_name?: string; email?: string };
}

function ok() {
	return jsonResponse(200, {});
}

describe('updateProfile action', () => {
	it('PATCHes /users/me with the profile fields and reports success', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () => ok());
		const result = (await actions.updateProfile(
			fakeActionEvent({
				form: { full_name: 'New Name', email: 'new@example.com' },
				locals: { session: 'jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.updateProfile>[0]
		)) as AccountData;

		const req = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(req.method).toBe('PATCH');
		expect(req.url).toBe('http://localhost:8000/api/v1/users/me');
		await expect(req.json()).resolves.toEqual({ full_name: 'New Name', email: 'new@example.com' });
		expect(result).toMatchObject({ intent: 'profile', success: true });
	});

	it('maps a 409 to an "email already in use" field error', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(409, { detail: 'User with this email already exists' })
		);
		const failure = (await actions.updateProfile(
			fakeActionEvent({
				form: { full_name: 'X', email: 'taken@example.com' },
				locals: { session: 'jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.updateProfile>[0]
		)) as ActionFailure<AccountData>;
		expect(failure.status).toBe(409);
		expect(failure.data.fieldErrors?.email).toBeTruthy();
		expect(failure.data.values?.email).toBe('taken@example.com');
	});
});

describe('changePassword action', () => {
	it('PATCHes /users/me/password and reports success', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { message: 'Password updated successfully' })
		);
		const result = (await actions.changePassword(
			fakeActionEvent({
				form: { current_password: 'oldpassword', new_password: 'newpassword' },
				locals: { session: 'jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.changePassword>[0]
		)) as AccountData;
		const req = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(req.method).toBe('PATCH');
		expect(req.url).toBe('http://localhost:8000/api/v1/users/me/password');
		await expect(req.json()).resolves.toEqual({
			current_password: 'oldpassword',
			new_password: 'newpassword'
		});
		expect(result).toMatchObject({ intent: 'password', success: true });
	});

	it('enforces the 8-char minimum before calling the backend', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () => ok());
		const failure = (await actions.changePassword(
			fakeActionEvent({
				form: { current_password: 'oldpassword', new_password: 'short' },
				locals: { session: 'jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.changePassword>[0]
		)) as ActionFailure<AccountData>;
		expect(fetchMock).not.toHaveBeenCalled();
		expect(failure.status).toBe(400);
		expect(failure.data.fieldErrors?.new_password).toBeTruthy();
	});

	it('maps a 400 "Incorrect password" to the current-password field', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(400, { detail: 'Incorrect password' })
		);
		const failure = (await actions.changePassword(
			fakeActionEvent({
				form: { current_password: 'wrongpass1', new_password: 'newpassword' },
				locals: { session: 'jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.changePassword>[0]
		)) as ActionFailure<AccountData>;
		expect(failure.status).toBe(400);
		expect(failure.data.fieldErrors?.current_password).toMatch(/incorrect/i);
	});

	it('maps a 400 "same as current" to the new-password field', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(400, { detail: 'New password cannot be the same as the current one' })
		);
		const failure = (await actions.changePassword(
			fakeActionEvent({
				form: { current_password: 'samepassword', new_password: 'samepassword' },
				locals: { session: 'jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.changePassword>[0]
		)) as ActionFailure<AccountData>;
		expect(failure.status).toBe(400);
		expect(failure.data.fieldErrors?.new_password).toMatch(/current/i);
	});
});

describe('deleteAccount action', () => {
	it('deletes the account, clears the session cookie, and redirects to the landing', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { message: 'User deleted successfully' })
		);
		const deleteCookie = vi.fn();
		let redirected: { status: number; location: string } | undefined;
		try {
			await actions.deleteAccount(
				fakeActionEvent({
					form: { confirm: 'on' },
					locals: { session: 'jwt', user: fakeUser() },
					cookies: { delete: deleteCookie },
					fetch: fetchMock as unknown as typeof fetch
				}) as Parameters<typeof actions.deleteAccount>[0]
			);
		} catch (e) {
			if (isRedirect(e)) {
				redirected = { status: e.status, location: e.location };
			} else {
				throw e;
			}
		}
		expect(fetchMock.mock.calls[0][0]).toBeDefined();
		expect((fetchMock.mock.calls[0][0] as unknown as Request).method).toBe('DELETE');
		expect(deleteCookie).toHaveBeenCalledWith('pp_session', { path: '/' });
		expect(redirected).toEqual({ status: 303, location: '/' });
	});

	it('surfaces the backend 403 when a superuser tries to self-delete', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(403, { detail: 'Super users are not allowed to delete themselves' })
		);
		const deleteCookie = vi.fn();
		const failure = (await actions.deleteAccount(
			fakeActionEvent({
				form: { confirm: 'on' },
				locals: { session: 'jwt', user: fakeUser({ is_superuser: true }) },
				cookies: { delete: deleteCookie },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.deleteAccount>[0]
		)) as ActionFailure<AccountData>;
		expect(failure.status).toBe(403);
		expect(failure.data.error).toBeTruthy();
		expect(deleteCookie).not.toHaveBeenCalled();
	});
});
