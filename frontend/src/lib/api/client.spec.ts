import { describe, expect, it, vi } from 'vitest';

// client.ts imports `$env/dynamic/private` at module load; stub it so the pure
// factory under test does not require the SvelteKit env to be wired.
vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { createApiClient, serverApiClient } = await import('./client');

function okJson() {
	return new Response('{}', {
		status: 200,
		headers: { 'content-type': 'application/json' }
	});
}

describe('createApiClient', () => {
	it('forwards the bearer as Authorization on backend requests', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(() => Promise.resolve(okJson()));
		const client = createApiClient({
			baseUrl: 'http://backend:8000',
			bearer: 'jwt-abc',
			fetch: fetchMock as unknown as typeof fetch
		});

		await client.GET('/api/v1/users/me');

		expect(fetchMock).toHaveBeenCalledOnce();
		const request = fetchMock.mock.calls[0][0];
		expect(request.headers.get('authorization')).toBe('Bearer jwt-abc');
		expect(request.url).toBe('http://backend:8000/api/v1/users/me');
	});

	it('sends no Authorization header when no bearer is provided', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(() => Promise.resolve(okJson()));
		const client = createApiClient({
			baseUrl: 'http://backend:8000',
			fetch: fetchMock as unknown as typeof fetch
		});

		await client.GET('/api/v1/observation/');

		const request = fetchMock.mock.calls[0][0];
		expect(request.headers.get('authorization')).toBeNull();
	});
});

describe('serverApiClient (optional-auth)', () => {
	it('forwards the bearer for a logged-in session (owner sees the enriched view)', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(() => Promise.resolve(okJson()));
		const client = serverApiClient(
			{ session: 'owner-jwt', user: null },
			fetchMock as unknown as typeof fetch
		);

		await client.GET('/api/v1/station/');

		const request = fetchMock.mock.calls[0][0];
		expect(request.headers.get('authorization')).toBe('Bearer owner-jwt');
	});

	it('sends no bearer for an anonymous request (only the public subset)', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(() => Promise.resolve(okJson()));
		const client = serverApiClient(
			{ session: null, user: null },
			fetchMock as unknown as typeof fetch
		);

		await client.GET('/api/v1/station/');

		const request = fetchMock.mock.calls[0][0];
		expect(request.headers.get('authorization')).toBeNull();
	});
});
