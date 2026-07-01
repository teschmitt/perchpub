import { requireUser } from '$lib/server/auth';
import type { LayoutServerLoad } from './$types';

/**
 * Authenticated zone guard. Runs server-side during `load`: redirects
 * unauthenticated requests to `/login?redirectTo=...` before any protected
 * content renders.
 *
 * P2 note: this guard requires only *a* user. P2's owner pages (`stations`,
 * `enroll`, `account`) deliberately do NOT apply `requireSuperuser` — ownership
 * is enforced per-row by the backend (`PUT /station/{id}`, `DELETE /users/me`).
 * The `requireSuperuser` helper (`$lib/server/auth`) is reserved for P3 admin areas.
 */
export const load: LayoutServerLoad = async ({ locals, url }) => {
	const user = requireUser(locals.user, url.pathname);
	return { user };
};
