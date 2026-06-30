import { requireUser } from '$lib/server/auth';
import type { LayoutServerLoad } from './$types';

/**
 * Authenticated zone guard. Runs server-side during `load`: redirects
 * unauthenticated requests to `/login?redirectTo=...` before any protected
 * content renders.
 */
export const load: LayoutServerLoad = async ({ locals, url }) => {
	const user = requireUser(locals.user, url.pathname);
	return { user };
};
