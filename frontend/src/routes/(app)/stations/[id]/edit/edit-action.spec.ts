import { isRedirect } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { actions } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

const STATION_ID = '11111111-1111-1111-1111-111111111111';

async function runDefault(event: Parameters<typeof actions.default>[0]) {
	try {
		return { failure: await actions.default(event) };
	} catch (e) {
		if (isRedirect(e)) {
			return { redirect: { status: e.status, location: e.location } };
		}
		throw e;
	}
}

function editEvent(form: Record<string, string>, fetchMock: typeof fetch) {
	return fakeActionEvent({
		form,
		params: { id: STATION_ID },
		locals: { session: 'owner-jwt', user: fakeUser() },
		fetch: fetchMock
	}) as Parameters<typeof actions.default>[0];
}

describe('edit-station action', () => {
	it('PUTs the COMPLETE station body to /station/{id} and redirects', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { id: STATION_ID })
		);
		const result = await runDefault(
			editEvent(
				{ latitude: '48.1', longitude: '11.6', is_private: 'on' },
				fetchMock as unknown as typeof fetch
			)
		);

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.method).toBe('PUT');
		expect(request.url).toBe(`http://localhost:8000/api/v1/station/${STATION_ID}`);
		await expect(request.json()).resolves.toEqual({
			latitude: 48.1,
			longitude: 11.6,
			is_private: true
		});
		expect(result.redirect).toEqual({ status: 303, location: '/stations/mine' });
	});

	it('surfaces a 403 (foreign public station) as an access-denied state', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(403, { detail: 'Not enough permissions' })
		);
		const result = await runDefault(
			editEvent({ latitude: '48.1', longitude: '11.6' }, fetchMock as unknown as typeof fetch)
		);
		expect(result.failure?.status).toBe(403);
		expect(result.failure?.data?.forbidden).toBe(true);
	});

	it('surfaces a 404 (foreign private / unknown station) as a not-found state', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(404, { detail: 'Station not found' })
		);
		const result = await runDefault(
			editEvent({ latitude: '48.1', longitude: '11.6' }, fetchMock as unknown as typeof fetch)
		);
		expect(result.failure?.status).toBe(404);
		expect(result.failure?.data?.notFound).toBe(true);
	});

	it('rejects out-of-range coordinates before calling the backend', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () => jsonResponse(200));
		const result = await runDefault(
			editEvent({ latitude: '-91', longitude: '11.6' }, fetchMock as unknown as typeof fetch)
		);
		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.failure?.status).toBe(400);
		expect(result.failure?.data?.errors?.latitude).toMatch(/-90/);
	});
});
