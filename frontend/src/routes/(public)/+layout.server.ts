import type { LayoutServerLoad } from './$types';

/**
 * Public zone: no auth guard. Expose the (optionally present) user so the nav
 * can reflect signed-in state. Optional-user DATA loads on public pages use
 * `serverApiClient(locals)`, which forwards the bearer only when a session
 * cookie is present (anonymous visitors get the public subset).
 */
export const load: LayoutServerLoad = async ({ locals }) => {
	return { user: locals.user };
};
