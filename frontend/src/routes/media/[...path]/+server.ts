import { error, isHttpError, type RequestHandler } from '@sveltejs/kit';
import { internalApiUrl } from '$lib/api/client';

/**
 * Same-origin media pass-through. Streams the backend media endpoint
 * (`GET /api/v1/media/{object_name}`) over the internal network so that
 * `<img>` / `<video>` sources are plain same-origin `/media/...` URLs. No auth
 * is required in P0; `Content-Type` and the immutable `Cache-Control` from the
 * backend are forwarded so the browser caches content-addressed media.
 */
export const GET: RequestHandler = async ({ params, fetch }) => {
	const path = params.path;
	if (!path) {
		error(404, 'Not found');
	}

	try {
		const upstream = await fetch(`${internalApiUrl()}/api/v1/media/${path}`);
		if (!upstream.ok) {
			// A missing object surfaces as the backend's 404; anything else is an
			// upstream failure.
			error(upstream.status === 404 ? 404 : 502, 'Media not found');
		}

		const headers = new Headers();
		for (const name of ['content-type', 'cache-control', 'content-length']) {
			const value = upstream.headers.get(name);
			if (value) {
				headers.set(name, value);
			}
		}
		return new Response(upstream.body, { status: 200, headers });
	} catch (e) {
		// Re-raise our own mapped HTTP errors; a thrown fetch (backend
		// unreachable) becomes a clean 502 rather than a leaked 500.
		if (isHttpError(e)) {
			throw e;
		}
		error(502, 'Media upstream unavailable');
	}
};
