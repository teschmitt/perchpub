import { type ActionFailure } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { load, actions } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

type FetchMock = ReturnType<typeof vi.fn<(input: Request) => Promise<Response>>>;
type TestEmailEvent = Parameters<(typeof actions)['test-email']>[0];

interface OpsData {
	message?: string;
	error?: string;
}

const superLocals = { session: 'super-jwt', user: fakeUser({ is_superuser: true }) };

describe('admin ops load (health-check)', () => {
	it('reports healthy when GET /utils/health-check/ returns true', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, true));
		const event = fakeActionEvent({
			url: 'http://localhost/admin/ops',
			locals: superLocals,
			fetch: fetchMock as unknown as typeof fetch
		});

		const data = (await load(event as unknown as Parameters<typeof load>[0])) as {
			healthy: boolean;
		};

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.url).toBe('http://localhost:8000/api/v1/utils/health-check/');
		expect(data.healthy).toBe(true);
	});

	it('reports unhealthy when the health-check responds 200 but not true', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, false));
		const event = fakeActionEvent({
			url: 'http://localhost/admin/ops',
			locals: superLocals,
			fetch: fetchMock as unknown as typeof fetch
		});

		const data = (await load(event as unknown as Parameters<typeof load>[0])) as {
			healthy: boolean;
		};
		expect(data.healthy).toBe(false);
	});

	it('reports unhealthy when the backend is unreachable (fetch throws)', async () => {
		const fetchMock: FetchMock = vi.fn(async () => {
			throw new Error('ECONNREFUSED');
		});
		const event = fakeActionEvent({
			url: 'http://localhost/admin/ops',
			locals: superLocals,
			fetch: fetchMock as unknown as typeof fetch
		});

		const data = (await load(event as unknown as Parameters<typeof load>[0])) as {
			healthy: boolean;
		};
		expect(data.healthy).toBe(false);
	});
});

describe('admin test-email action', () => {
	function emailEvent(form: Record<string, string | undefined>, fetchMock: FetchMock) {
		return fakeActionEvent({
			form,
			locals: superLocals,
			fetch: fetchMock as unknown as typeof fetch
		}) as unknown as TestEmailEvent;
	}

	it('POSTs /utils/test-email/ with the email_to query param and returns the backend message', async () => {
		const fetchMock: FetchMock = vi.fn(async () =>
			jsonResponse(201, { message: 'Test email sent' })
		);
		const result = (await actions['test-email'](
			emailEvent({ email_to: 'ops@example.com' }, fetchMock)
		)) as OpsData;

		const request = fetchMock.mock.calls[0][0] as unknown as Request;
		expect(request.method).toBe('POST');
		const url = new URL(request.url);
		expect(url.pathname).toBe('/api/v1/utils/test-email/');
		expect(url.searchParams.get('email_to')).toBe('ops@example.com');
		expect(result.message).toBe('Test email sent');
	});

	it('surfaces the backend {detail} when the send fails (e.g. email not configured)', async () => {
		const fetchMock: FetchMock = vi.fn(async () =>
			jsonResponse(500, { detail: 'Email not configured' })
		);
		const failure = (await actions['test-email'](
			emailEvent({ email_to: 'ops@example.com' }, fetchMock)
		)) as ActionFailure<OpsData>;

		expect(failure.data.error).toBeTruthy();
	});

	it('rejects an empty address without calling the backend', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(201, {}));
		const failure = (await actions['test-email'](
			emailEvent({}, fetchMock)
		)) as ActionFailure<OpsData>;

		expect(fetchMock).not.toHaveBeenCalled();
		expect(failure.status).toBe(400);
	});
});
