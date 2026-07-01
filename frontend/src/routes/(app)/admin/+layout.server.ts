import { requireSuperuser } from '$lib/server/auth';
import type { LayoutServerLoad } from './$types';

/**
 * Superuser zone guard (P3). Nested under the `(app)` authed layout, it runs
 * server-side during `load` for every `admin/*` route: an anonymous request is
 * redirected to `/login`; an authenticated non-superuser gets a `404` (so admin
 * routes don't leak their existence) — all before any admin data is fetched.
 * The backend's `get_current_active_superuser` on `/users/*` and
 * `PUT /observation/{id}` stays in force as defense-in-depth.
 */
export const load: LayoutServerLoad = async ({ locals, url }) => {
	const user = requireSuperuser(locals.user, url.pathname);
	return { user };
};
