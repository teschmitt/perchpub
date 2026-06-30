import type { SessionUser } from '$lib/api/client';

export interface ResolvedSession {
	/** The session JWT to keep on `locals`, or null when anonymous. */
	session: string | null;
	/** The resolved user, or null when anonymous. */
	user: SessionUser | null;
	/** Whether the caller should delete the `pp_session` cookie this response. */
	clearCookie: boolean;
}

/** Result of fetching `/users/me` with a candidate token. */
export interface UserFetchResult {
	status: number;
	user: SessionUser | null;
}

/**
 * Decide the per-request session state from the raw cookie token.
 *
 * - No token → anonymous (the backend is never called).
 * - Backend `401` (expired/invalid token) → clear the cookie and treat as
 *   anonymous. Clearing the cookie is ALL that happens here; redirecting to
 *   `/login` is the `(app)` guard's job, so a stale cookie on a public page
 *   degrades to anonymous without forcing a logout.
 * - Otherwise → the resolved user (or anonymous if the backend returned none).
 */
export async function resolveSession(
	token: string | undefined,
	fetchUser: (token: string) => Promise<UserFetchResult>
): Promise<ResolvedSession> {
	if (!token) {
		return { session: null, user: null, clearCookie: false };
	}
	const { status, user } = await fetchUser(token);
	if (status === 401) {
		return { session: null, user: null, clearCookie: true };
	}
	return { session: token, user, clearCookie: false };
}
