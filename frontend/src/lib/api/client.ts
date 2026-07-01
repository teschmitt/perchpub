import { error, isHttpError, isRedirect } from '@sveltejs/kit';
import createClient, { type Client } from 'openapi-fetch';
import { env } from '$env/dynamic/private';
import type { components, paths } from './schema';

/** The authenticated user as returned by the backend `/users/me`. */
export type SessionUser = components['schemas']['UserPublic'];

const DEFAULT_INTERNAL_API_URL = 'http://localhost:8000';

export interface ApiClientOptions {
	/** Backend origin on the internal network, e.g. `http://backend:8000` (no `/api/v1`). */
	baseUrl: string;
	/** Session JWT. When set, attached as `Authorization: Bearer` on every request. */
	bearer?: string;
	/** Custom fetch (pass SvelteKit's `event.fetch` from server `load`). */
	fetch?: typeof globalThis.fetch;
}

/**
 * Pure factory for the typed backend client. Kept free of SvelteKit env so it
 * is unit-testable in isolation. The bearer — when provided — is the ONLY place
 * the JWT is forwarded to the backend; it is never exposed to the browser.
 */
export function createApiClient(options: ApiClientOptions): Client<paths> {
	const headers: Record<string, string> = {};
	if (options.bearer) {
		headers.Authorization = `Bearer ${options.bearer}`;
	}
	return createClient<paths>({
		baseUrl: options.baseUrl,
		headers,
		...(options.fetch ? { fetch: options.fetch } : {})
	});
}

/** Backend origin from `INTERNAL_API_URL` (server-only), with a dev default. */
export function internalApiUrl(): string {
	return env.INTERNAL_API_URL || DEFAULT_INTERNAL_API_URL;
}

/**
 * Server-side helper: a client bound to the current request's session. Forwards
 * the bearer only when a session is present (`locals.session`), which is how
 * optional-auth public pages stay anonymous-capable yet enriched when logged in.
 */
export function serverApiClient(
	locals: App.Locals,
	fetcher?: typeof globalThis.fetch
): Client<paths> {
	return createApiClient({
		baseUrl: internalApiUrl(),
		bearer: locals.session ?? undefined,
		fetch: fetcher
	});
}

/**
 * Await an openapi-fetch call, mapping a THROWN fetch (backend unreachable /
 * network failure — openapi-fetch resolves on HTTP 4xx/5xx but rejects on a
 * transport error) to a clean `502`, mirroring the media pass-through endpoint.
 * A load then surfaces its intended error contract instead of a generic `500`.
 * SvelteKit control-flow throws (`error()`/`redirect()`) are re-raised unchanged.
 */
export async function requestUpstream<T>(call: Promise<T>): Promise<T> {
	try {
		return await call;
	} catch (e) {
		if (isHttpError(e) || isRedirect(e)) {
			throw e;
		}
		error(502, 'Backend unavailable');
	}
}
