import { isRedirect } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { load, actions } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

type LoadEvent = Parameters<typeof load>[0];
type CreateEvent = Parameters<typeof actions.create>[0];
type DeleteEvent = Parameters<typeof actions.delete>[0];
type FetchMock = ReturnType<typeof vi.fn<(input: Request) => Promise<Response>>>;

async function runCreate(event: CreateEvent) {
	try {
		return { failure: await actions.create(event) };
	} catch (e) {
		if (isRedirect(e)) return { redirect: { status: e.status, location: e.location } };
		throw e;
	}
}

async function runDelete(event: DeleteEvent) {
	try {
		return { failure: await actions.delete(event) };
	} catch (e) {
		if (isRedirect(e)) return { redirect: { status: e.status, location: e.location } };
		throw e;
	}
}

describe('admin users load', () => {
	it('returns the UsersPublic {data,count} from GET /users/', async () => {
		const users = [fakeUser({ id: 'u1', email: 'a@example.com' })];
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { data: users, count: 1 }));
		const event = fakeActionEvent({
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			url: 'http://localhost/admin/users',
			fetch: fetchMock as unknown as typeof fetch
		});

		const data = (await load(event as unknown as LoadEvent)) as { items: unknown[]; count: number };

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.method).toBe('GET');
		expect(request.url).toMatch(/\/api\/v1\/users\/\?/);
		expect(request.headers.get('authorization')).toBe('Bearer super-jwt');
		expect(data.items).toEqual(users);
		expect(data.count).toBe(1);
	});
});

describe('admin create-user action', () => {
	it('POSTs a complete UserCreate through the typed client and redirects to the list', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { id: 'u-new' }));
		const event = fakeActionEvent({
			form: {
				email: 'new@example.com',
				password: 'hunter2hunter2',
				full_name: 'New User',
				is_active: 'on'
			},
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			fetch: fetchMock as unknown as typeof fetch
		});

		const result = await runCreate(event as unknown as CreateEvent);

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.method).toBe('POST');
		expect(request.url).toBe('http://localhost:8000/api/v1/users/');
		await expect(request.json()).resolves.toEqual({
			email: 'new@example.com',
			password: 'hunter2hunter2',
			full_name: 'New User',
			is_active: true,
			is_superuser: false
		});
		expect(result.redirect).toEqual({ status: 303, location: '/admin/users' });
	});

	it('surfaces the backend 400 duplicate-email {detail} as a form error and does not redirect', async () => {
		const detail = 'The user with this email already exists in the system.';
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(400, { detail }));
		const event = fakeActionEvent({
			form: { email: 'dupe@example.com', password: 'hunter2hunter2' },
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			fetch: fetchMock as unknown as typeof fetch
		});

		const result = await runCreate(event as unknown as CreateEvent);

		expect(result.redirect).toBeUndefined();
		expect(result.failure?.status).toBe(400);
		expect(result.failure?.data?.formError).toBe(detail);
		expect(result.failure?.data?.values?.email).toBe('dupe@example.com');
	});

	it('maps a non-400 backend failure (422) to a generic form error without redirecting', async () => {
		const fetchMock: FetchMock = vi.fn(async () =>
			jsonResponse(422, { detail: [{ msg: 'weak password' }] })
		);
		const event = fakeActionEvent({
			form: { email: 'x@example.com', password: 'short' },
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			fetch: fetchMock as unknown as typeof fetch
		});

		const result = await runCreate(event as unknown as CreateEvent);

		expect(result.redirect).toBeUndefined();
		expect(result.failure?.status).toBe(422);
		expect(result.failure?.data?.formError).toBeTruthy();
		expect(result.failure?.data?.values?.email).toBe('x@example.com');
	});
});

describe('admin delete-user action', () => {
	it('DELETEs /users/{user_id} and redirects to the list', async () => {
		const fetchMock: FetchMock = vi.fn(async () =>
			jsonResponse(200, { message: 'User deleted successfully' })
		);
		const event = fakeActionEvent({
			form: { user_id: 'u-target' },
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			fetch: fetchMock as unknown as typeof fetch
		});

		const result = await runDelete(event as unknown as DeleteEvent);

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.method).toBe('DELETE');
		expect(request.url).toBe('http://localhost:8000/api/v1/users/u-target');
		expect(result.redirect).toEqual({ status: 303, location: '/admin/users' });
	});

	it('surfaces the backend 403 self-delete {detail} without crashing', async () => {
		const detail = 'Super users are not allowed to delete themselves';
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(403, { detail }));
		const event = fakeActionEvent({
			form: { user_id: 'u-self' },
			locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
			fetch: fetchMock as unknown as typeof fetch
		});

		const result = await runDelete(event as unknown as DeleteEvent);

		expect(result.redirect).toBeUndefined();
		expect(result.failure?.status).toBe(403);
		expect(result.failure?.data?.error).toBe(detail);
	});
});
