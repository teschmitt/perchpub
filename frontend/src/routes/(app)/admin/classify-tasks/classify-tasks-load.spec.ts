import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { load } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

type FetchMock = ReturnType<typeof vi.fn<(input: Request) => Promise<Response>>>;

function runLoad(fetchMock: FetchMock, search = '') {
	const event = fakeActionEvent({
		url: `http://localhost/admin/classify-tasks${search}`,
		locals: { session: 'super-jwt', user: fakeUser({ is_superuser: true }) },
		fetch: fetchMock as unknown as typeof fetch
	});
	return load(event as unknown as Parameters<typeof load>[0]);
}

function requestQuery(fetchMock: FetchMock): URLSearchParams {
	const request = fetchMock.mock.calls[0][0] as unknown as Request;
	return new URL(request.url).searchParams;
}

describe('admin classify-tasks load', () => {
	it('passes the status and observation URL filters to GET /classify-task/', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { data: [], count: 0 }));
		await runLoad(fetchMock, '?status=Failed&observation=obs-9');

		const query = requestQuery(fetchMock);
		expect(query.get('status')).toBe('Failed');
		expect(query.get('observation')).toBe('obs-9');
	});

	it('drops an invalid status value rather than sending it', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { data: [], count: 0 }));
		await runLoad(fetchMock, '?status=Bogus');

		expect(requestQuery(fetchMock).has('status')).toBe(false);
	});

	it('sends no filter params when none are set', async () => {
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { data: [], count: 0 }));
		await runLoad(fetchMock);

		const query = requestQuery(fetchMock);
		expect(query.has('status')).toBe(false);
		expect(query.has('observation')).toBe(false);
	});

	it('returns the ClassifyTasksPublic data plus the active filters', async () => {
		const tasks = [{ id: 't1', status: 'Success', object_name: 'a/b/c.jpg' }];
		const fetchMock: FetchMock = vi.fn(async () => jsonResponse(200, { data: tasks, count: 1 }));
		const data = (await runLoad(fetchMock, '?status=Success')) as {
			items: unknown[];
			count: number;
			statusFilter: string | null;
		};

		expect(data.items).toEqual(tasks);
		expect(data.count).toBe(1);
		expect(data.statusFilter).toBe('Success');
	});
});
