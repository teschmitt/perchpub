import type { RequestEvent } from '@sveltejs/kit';
import type { SessionUser } from '$lib/api/client';

/**
 * Build a canned JSON `Response` for a `fetch` stub, so a form-action unit test
 * can drive the typed client's outcome (status + body) without a live backend.
 */
export function jsonResponse(status: number, body: unknown = {}): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

/** A minimal superuser/non-superuser `SessionUser` for `locals.user`. */
export function fakeUser(overrides: Partial<SessionUser> = {}): SessionUser {
	return {
		id: 'user-1',
		email: 'owner@example.com',
		is_active: true,
		is_superuser: false,
		full_name: 'Owner One',
		...overrides
	};
}

export interface FakeEventOptions {
	/** Form fields; a `null`/`undefined` value is omitted (models an absent checkbox). */
	form?: Record<string, string | null | undefined>;
	locals?: Partial<App.Locals>;
	params?: Record<string, string>;
	/** Full request URL; defaults to a local path. */
	url?: string;
	/** The `fetch` the typed client will call (assert the outgoing `Request` here). */
	fetch: typeof globalThis.fetch;
	cookies?: Partial<RequestEvent['cookies']>;
	/** Spy/override for `event.setHeaders`; defaults to a no-op. */
	setHeaders?: (headers: Record<string, string>) => void;
}

/**
 * Construct the subset of a SvelteKit `RequestEvent` that a `+page.server.ts`
 * form action reads (`request.formData()`, `locals`, `params`, `url`, `fetch`,
 * `cookies`). Cast to `RequestEvent` at the call site so the action's parameter
 * type is satisfied without stubbing the whole interface.
 */
export function fakeActionEvent(options: FakeEventOptions): RequestEvent {
	const fd = new FormData();
	for (const [key, value] of Object.entries(options.form ?? {})) {
		if (value !== null && value !== undefined) {
			fd.append(key, value);
		}
	}
	const cookies = {
		get: () => undefined,
		getAll: () => [],
		set: () => {},
		delete: () => {},
		serialize: () => '',
		...options.cookies
	};
	const event = {
		request: { formData: async () => fd } as unknown as Request,
		locals: { session: null, user: null, ...options.locals } as App.Locals,
		params: options.params ?? {},
		url: new URL(options.url ?? 'http://localhost/'),
		fetch: options.fetch,
		setHeaders: options.setHeaders ?? (() => {}),
		cookies
	};
	return event as unknown as RequestEvent;
}
