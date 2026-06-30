import { describe, expect, it, vi } from 'vitest';
import type { SessionUser } from '$lib/api/client';
import { resolveSession } from './session';

const user: SessionUser = {
	id: '00000000-0000-0000-0000-000000000001',
	email: 'owner@example.com',
	is_active: true,
	is_superuser: false,
	full_name: null
};

describe('resolveSession', () => {
	it('treats a missing token as anonymous without calling the backend', async () => {
		const fetchUser = vi.fn();
		const result = await resolveSession(undefined, fetchUser);
		expect(result).toEqual({ session: null, user: null, clearCookie: false });
		expect(fetchUser).not.toHaveBeenCalled();
	});

	it('resolves the user for a valid token', async () => {
		const result = await resolveSession('jwt', async () => ({ status: 200, user }));
		expect(result).toEqual({ session: 'jwt', user, clearCookie: false });
	});

	it('clears the cookie when the backend rejects the token with 401', async () => {
		const result = await resolveSession('stale', async () => ({ status: 401, user: null }));
		expect(result).toEqual({ session: null, user: null, clearCookie: true });
	});
});
