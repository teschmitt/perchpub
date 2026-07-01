import { isRedirect } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { actions } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

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

describe('create-station action', () => {
	it('POSTs the parsed station body and redirects to the station list', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { id: 's-new' })
		);
		const event = fakeActionEvent({
			form: { latitude: '52.5', longitude: '13.4', is_private: 'on' },
			locals: { session: 'owner-jwt', user: fakeUser() },
			fetch: fetchMock as unknown as typeof fetch
		});

		const result = await runDefault(event as Parameters<typeof actions.default>[0]);

		expect(fetchMock).toHaveBeenCalledOnce();
		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.method).toBe('POST');
		expect(request.url).toBe('http://localhost:8000/api/v1/station/');
		expect(request.headers.get('authorization')).toBe('Bearer owner-jwt');
		await expect(request.json()).resolves.toEqual({
			latitude: 52.5,
			longitude: 13.4,
			is_private: true
		});
		expect(result.redirect).toEqual({ status: 303, location: '/stations/mine' });
	});

	it('rejects out-of-range coordinates without calling the backend', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () => jsonResponse(200));
		const event = fakeActionEvent({
			form: { latitude: '999', longitude: '13.4' },
			locals: { session: 'owner-jwt', user: fakeUser() },
			fetch: fetchMock as unknown as typeof fetch
		});

		const result = await runDefault(event as Parameters<typeof actions.default>[0]);

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.failure?.status).toBe(400);
		expect(result.failure?.data?.errors?.latitude).toMatch(/-90/);
		expect(result.failure?.data?.values).toEqual({
			latitude: '999',
			longitude: '13.4',
			is_private: false
		});
	});

	it('maps a backend 422 to a form-level error that re-renders the values', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(422, { detail: [{ msg: 'bad', loc: ['body', 'latitude'] }] })
		);
		const event = fakeActionEvent({
			form: { latitude: '52.5', longitude: '13.4' },
			locals: { session: 'owner-jwt', user: fakeUser() },
			fetch: fetchMock as unknown as typeof fetch
		});

		const result = await runDefault(event as Parameters<typeof actions.default>[0]);

		expect(result.failure?.status).toBe(422);
		expect(result.failure?.data?.formError).toBeTruthy();
		expect(result.failure?.data?.values?.latitude).toBe('52.5');
	});
});
