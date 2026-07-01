import { isHttpError, isRedirect } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { load, actions } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

type UpdateEvent = Parameters<typeof actions.update>[0];
type FetchMock = ReturnType<typeof vi.fn<(input: Request) => Promise<Response>>>;

async function runUpdate(event: unknown) {
	try {
		return { failure: await actions.update(event as UpdateEvent) };
	} catch (e) {
		if (isRedirect(e)) return { redirect: { status: e.status, location: e.location } };
		throw e;
	}
}

describe('admin edit-user load', () => {
	it('prefills from GET /users/{user_id}', async () => {
		const target = fakeUser({ id: 'u-target', email: 'target@example.com' });
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, target));
		const event = fakeActionEvent({
			params: { id: 'u-target' },
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			fetch: fetchMock as unknown as typeof fetch
		});

		const data = (await load(event as unknown as Parameters<typeof load>[0])) as {
			editUser: { email: string };
		};

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.method).toBe('GET');
		expect(request.url).toBe('http://localhost:8000/api/v1/users/u-target');
		expect(data.editUser).toEqual(target);
	});

	it('renders 404 when the user does not exist', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(404, { detail: 'not found' }));
		const event = fakeActionEvent({
			params: { id: 'u-missing' },
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			fetch: fetchMock as unknown as typeof fetch
		});

		try {
			await load(event as unknown as Parameters<typeof load>[0]);
			expect.unreachable('load should 404');
		} catch (e) {
			expect(isHttpError(e) && e.status).toBe(404);
		}
	});
});

describe('admin update-user action', () => {
	function updateEvent(form: Record<string, string | undefined>, fetchMock: unknown) {
		return fakeActionEvent({
			form,
			params: { id: 'u-target' },
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			fetch: fetchMock as unknown as typeof fetch
		});
	}

	it('PATCHes a UserUpdate carrying is_active=false to deactivate, then redirects', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { id: 'u-target' }));
		// is_active checkbox unchecked → absent → false.
		const event = updateEvent({ email: 'target@example.com' }, fetchMock);

		const result = await runUpdate(event);

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.method).toBe('PATCH');
		expect(request.url).toBe('http://localhost:8000/api/v1/users/u-target');
		const body = (await request.json()) as Record<string, unknown>;
		expect(body.is_active).toBe(false);
		expect(body.is_superuser).toBe(false);
		expect(body).not.toHaveProperty('password');
		expect(result.redirect).toEqual({ status: 303, location: '/admin/users' });
	});

	it('PATCHes is_superuser=true when the superuser toggle is set', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { id: 'u-target' }));
		const event = updateEvent(
			{ email: 'target@example.com', is_active: 'on', is_superuser: 'on' },
			fetchMock
		);

		await runUpdate(event);

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		const body = (await request.json()) as Record<string, unknown>;
		expect(body.is_active).toBe(true);
		expect(body.is_superuser).toBe(true);
	});

	it('includes password only when a new one is supplied', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { id: 'u-target' }));
		const event = updateEvent(
			{ email: 'target@example.com', is_active: 'on', password: 'brandnewpass' },
			fetchMock
		);

		await runUpdate(event);

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		const body = (await request.json()) as Record<string, unknown>;
		expect(body.password).toBe('brandnewpass');
	});

	it('surfaces a backend 409 duplicate-email as a field error', async () => {
		const fetchMock: FetchMock = vi.fn(async () =>
			jsonResponse(409, { detail: 'User with this email already exists' })
		);
		const event = updateEvent({ email: 'taken@example.com', is_active: 'on' }, fetchMock);

		const result = await runUpdate(event);

		expect(result.redirect).toBeUndefined();
		expect(result.failure?.status).toBe(409);
		expect(result.failure?.data?.fieldErrors?.email).toBeTruthy();
	});
});
