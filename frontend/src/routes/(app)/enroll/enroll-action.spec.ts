import type { ActionFailure } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';
import type { EnrollResult } from '$lib/enrollment';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { actions } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

const SESSION = {
	session_id: '22222222-2222-2222-2222-222222222222',
	auth_token: 'one-time-secret-token',
	ca_pin: 'b'.repeat(64),
	expires_at: '2026-07-01T12:05:00.000Z'
};

function ownedStation(id: string) {
	return {
		id,
		latitude: 1,
		longitude: 2,
		is_private: false,
		owner: { id: 'user-1', full_name: null }
	};
}

describe('enroll create action', () => {
	it('POSTs coordinates to /enrollment/create and surfaces the one-time session', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async (req) => {
			if (req.url.endsWith('/api/v1/enrollment/create')) {
				return jsonResponse(200, SESSION);
			}
			// baseline fetch: operator already owns one station
			return jsonResponse(200, { data: [ownedStation('s-existing')], count: 1 });
		});

		const setHeaders = vi.fn();
		const result = (await actions.create(
			fakeActionEvent({
				form: { latitude: '52.5', longitude: '13.4' },
				locals: { session: 'owner-jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch,
				setHeaders
			}) as Parameters<typeof actions.create>[0]
		)) as EnrollResult;

		// The one-time credential ride must never be cached (spec: served no-store).
		expect(setHeaders).toHaveBeenCalledWith({ 'cache-control': 'no-store' });

		const createReq = fetchMock.mock.calls.find((c) =>
			(c[0] as unknown as Request).url.endsWith('/api/v1/enrollment/create')
		)![0] as unknown as Request;
		expect(createReq.method).toBe('POST');
		await expect(createReq.json()).resolves.toEqual({ latitude: 52.5, longitude: 13.4 });

		expect(result).toMatchObject({
			intent: 'create',
			session: {
				session_id: SESSION.session_id,
				auth_token: SESSION.auth_token,
				ca_pin: SESSION.ca_pin,
				expires_at: SESSION.expires_at
			},
			baseline: ['s-existing']
		});
	});

	it('rejects invalid coordinates without starting a session', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () => jsonResponse(200));
		const failure = (await actions.create(
			fakeActionEvent({
				form: { latitude: '999', longitude: '0' },
				locals: { session: 'owner-jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.create>[0]
		)) as ActionFailure<EnrollResult>;
		expect(fetchMock).not.toHaveBeenCalled();
		expect(failure.status).toBe(400);
		expect(failure.data.errors?.latitude).toMatch(/-90/);
	});
});

describe('enroll check action', () => {
	it('reports the newly enrolled station when the list has grown', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { data: [ownedStation('s-existing'), ownedStation('s-new')], count: 2 })
		);
		const result = (await actions.check(
			fakeActionEvent({
				form: { baseline: JSON.stringify(['s-existing']) },
				locals: { session: 'owner-jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.check>[0]
		)) as EnrollResult;
		expect(result).toMatchObject({ intent: 'check', newStationId: 's-new' });
	});

	it('reports no new station when nothing has appeared yet', async () => {
		const fetchMock = vi.fn<(input: Request) => Promise<Response>>(async () =>
			jsonResponse(200, { data: [ownedStation('s-existing')], count: 1 })
		);
		const result = (await actions.check(
			fakeActionEvent({
				form: { baseline: JSON.stringify(['s-existing']) },
				locals: { session: 'owner-jwt', user: fakeUser() },
				fetch: fetchMock as unknown as typeof fetch
			}) as Parameters<typeof actions.check>[0]
		)) as EnrollResult;
		expect(result).toMatchObject({ intent: 'check', newStationId: null });
	});
});
