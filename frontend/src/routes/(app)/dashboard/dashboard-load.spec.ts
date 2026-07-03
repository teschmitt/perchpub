import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { load } = await import('./+page.server');
const { fakeUser, jsonResponse } = await import('$lib/action-testing');

function station(id: string, ownerId: string) {
	return {
		id,
		latitude: 1,
		longitude: 2,
		is_private: false,
		owner: { id: ownerId, full_name: null }
	};
}

function fakeLoadEvent(fetchImpl: typeof globalThis.fetch, user = fakeUser()) {
	return {
		locals: { session: 'owner-jwt', user },
		fetch: fetchImpl
	} as unknown as Parameters<typeof load>[0];
}

describe('dashboard load — owned-station count (drives onboarding)', () => {
	it('reports zero when the user owns no stations', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { data: [], count: 0 })
		);
		const result = await load(fakeLoadEvent(fetchMock as unknown as typeof globalThis.fetch));
		expect(result).toEqual({ stationCount: 0 });
	});

	it('counts only the stations owned by the current user', async () => {
		const me = fakeUser({ id: 'user-1' });
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, {
				data: [station('s1', 'user-1'), station('s2', 'someone-else'), station('s3', 'user-1')],
				count: 3
			})
		);
		const result = await load(fakeLoadEvent(fetchMock as unknown as typeof globalThis.fetch, me));
		expect(result).toEqual({ stationCount: 2 });
	});

	it('surfaces a 502 when the station list cannot be loaded', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(502, {})
		);
		await expect(
			load(fakeLoadEvent(fetchMock as unknown as typeof globalThis.fetch))
		).rejects.toMatchObject({ status: 502 });
	});
});
