import { type ActionFailure, isHttpError } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));
vi.mock('$env/dynamic/public', () => ({ env: {} }));

const { load, actions } = await import('./+page.server');
const { fakeActionEvent, fakeUser, jsonResponse } = await import('$lib/action-testing');

type ReclassifyEvent = Parameters<typeof actions.reclassify>[0];

interface ReclassifyData {
	reclassified?: boolean;
	reclassifyError?: string;
}

/** A canned observation body for `GET /observation/{id}`. */
const OBSERVATION = {
	id: 'obs-1',
	confidence_score: 0.91,
	classification_result: [['Passer domesticus', 0.91]],
	species: null,
	station: { id: 'st-1', latitude: 1, longitude: 2, is_private: false, owner: null },
	observed_at: '2026-06-30T09:30:00+00:00',
	object_name: 'ab/cd/x.jpg'
};

/**
 * A fetch stub that routes by method + path, so a single test can serve the
 * observation GET, the classify-task GET, the species GET, and the observation PUT.
 */
function routeFetch(
	overrides: {
		observation?: Response;
		put?: Response;
		classifyTasks?: Response;
		species?: Response;
	} = {}
) {
	return vi.fn<(input: Request) => Promise<Response>>(async (input: Request) => {
		const req = input as unknown as Request;
		const path = new URL(req.url).pathname;
		if (req.method === 'PUT' && path.startsWith('/api/v1/observation/')) {
			return overrides.put ?? jsonResponse(200, OBSERVATION);
		}
		if (path.startsWith('/api/v1/observation/')) {
			return overrides.observation ?? jsonResponse(200, OBSERVATION);
		}
		if (path.startsWith('/api/v1/classify-task/')) {
			return overrides.classifyTasks ?? jsonResponse(200, { data: [], count: 0 });
		}
		if (path.startsWith('/api/v1/species/')) {
			return overrides.species ?? jsonResponse(200, { data: [], count: 0 });
		}
		throw new Error(`unexpected request: ${req.method} ${path}`);
	});
}

function reclassifyEvent(
	form: Record<string, string | undefined>,
	fetchMock: unknown,
	user = fakeUser({ is_superuser: true })
) {
	return fakeActionEvent({
		form,
		params: { id: 'obs-1' },
		locals: { session: user ? 'jwt' : null, user },
		fetch: fetchMock as unknown as typeof fetch
	}) as unknown as ReclassifyEvent;
}

describe('observation reclassify action', () => {
	it('PUTs a COMPLETE ObservationUpdate, carrying confidence_score + classification_result unchanged', async () => {
		const fetchMock = routeFetch();
		const result = (await actions.reclassify(
			reclassifyEvent({ species_id: 'sp-42' }, fetchMock)
		)) as ReclassifyData;

		const put = fetchMock.mock.calls
			.map((c) => c[0] as unknown as Request)
			.find((r) => r.method === 'PUT')!;
		expect(put.url).toBe('http://localhost:8000/api/v1/observation/obs-1');
		await expect(put.json()).resolves.toEqual({
			species_id: 'sp-42',
			manually_classified: true,
			confidence_score: 0.91,
			classification_result: [['Passer domesticus', 0.91]]
		});
		expect(result.reclassified).toBe(true);
	});

	it('does not call the backend when no species is chosen', async () => {
		const fetchMock = routeFetch();
		const failure = (await actions.reclassify(
			reclassifyEvent({}, fetchMock)
		)) as ActionFailure<ReclassifyData>;

		expect(fetchMock).not.toHaveBeenCalled();
		expect(failure.data.reclassifyError).toBeTruthy();
	});

	it('surfaces a backend 403 (non-superuser) as a form error and does not report success', async () => {
		const fetchMock = routeFetch({
			put: jsonResponse(403, { detail: 'The user does not have enough privileges' })
		});
		const failure = (await actions.reclassify(
			reclassifyEvent({ species_id: 'sp-42' }, fetchMock)
		)) as ActionFailure<ReclassifyData>;

		expect(failure.status).toBe(403);
		expect(failure.data.reclassifyError).toBe('The user does not have enough privileges');
	});

	it('maps a non-403 backend rejection (422) to a generic error without reporting success', async () => {
		const fetchMock = routeFetch({ put: jsonResponse(422, { detail: 'invalid species_id' }) });
		const failure = (await actions.reclassify(
			reclassifyEvent({ species_id: 'sp-42' }, fetchMock)
		)) as ActionFailure<ReclassifyData>;

		expect(failure.status).toBe(422);
		expect(failure.data.reclassifyError).toBeTruthy();
		expect(failure.data.reclassified).toBeUndefined();
	});
});

describe('observation detail load', () => {
	async function runLoad(user: ReturnType<typeof fakeUser> | null, fetchMock: unknown) {
		const event = fakeActionEvent({
			params: { id: 'obs-1' },
			url: 'http://localhost/observations/obs-1',
			locals: { session: user ? 'jwt' : null, user },
			fetch: fetchMock as unknown as typeof fetch
		});
		return (await load(event as unknown as Parameters<typeof load>[0])) as {
			species: unknown[];
			latestStatus: string | null;
		};
	}

	it('derives latestStatus from the most-recent classify task', async () => {
		const fetchMock = routeFetch({
			classifyTasks: jsonResponse(200, { data: [{ status: 'Failed' }], count: 1 })
		});
		const data = await runLoad(fakeUser({ is_superuser: true }), fetchMock);
		expect(data.latestStatus).toBe('Failed');
	});

	it('shows no status (null) when the observation has no classify task', async () => {
		const fetchMock = routeFetch();
		const data = await runLoad(fakeUser({ is_superuser: true }), fetchMock);
		expect(data.latestStatus).toBeNull();
	});

	it('populates species for a superuser (for the reclassify control)', async () => {
		const fetchMock = routeFetch({
			species: jsonResponse(200, {
				data: [{ id: 'sp-1', scientific_name: 'Parus major' }],
				count: 1
			})
		});
		const data = await runLoad(fakeUser({ is_superuser: true }), fetchMock);
		expect(data.species).toHaveLength(1);
	});

	it('does NOT fetch species for an anonymous visitor', async () => {
		const fetchMock = routeFetch();
		const data = await runLoad(null, fetchMock);
		expect(data.species).toEqual([]);
		const paths = fetchMock.mock.calls.map(
			(c) => new URL((c[0] as unknown as Request).url).pathname
		);
		expect(paths.some((p) => p.startsWith('/api/v1/species/'))).toBe(false);
	});

	it('404s a missing observation', async () => {
		const fetchMock = routeFetch({ observation: jsonResponse(404, { detail: 'nope' }) });
		try {
			await runLoad(null, fetchMock);
			expect.unreachable('load should 404');
		} catch (e) {
			expect(isHttpError(e) && e.status).toBe(404);
		}
	});
});
