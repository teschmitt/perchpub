import { isHttpError, isRedirect } from '@sveltejs/kit';
import { describe, expect, it } from 'vitest';
import { fakeUser } from '$lib/action-testing';
import type { SessionUser } from '$lib/api/client';

const { load } = await import('./+layout.server');

function fakeLoadEvent(user: SessionUser | null, pathname = '/admin/users') {
	return {
		locals: { session: user ? 'jwt' : null, user },
		url: new URL(`http://localhost${pathname}`)
	} as unknown as Parameters<typeof load>[0];
}

async function runLoad(user: SessionUser | null, pathname?: string) {
	try {
		return { data: await load(fakeLoadEvent(user, pathname)) };
	} catch (e) {
		if (isRedirect(e)) return { redirect: { status: e.status, location: e.location } };
		if (isHttpError(e)) return { error: { status: e.status } };
		throw e;
	}
}

describe('(app)/admin superuser guard', () => {
	it('returns the user for an authenticated superuser', async () => {
		const superuser = fakeUser({ is_superuser: true });
		const result = await runLoad(superuser);
		expect(result.data?.user).toBe(superuser);
	});

	it('404s an authenticated non-superuser before any admin data loads', async () => {
		const result = await runLoad(fakeUser({ is_superuser: false }));
		expect(result.error?.status).toBe(404);
	});

	it('redirects an anonymous request to login carrying redirectTo', async () => {
		const result = await runLoad(null, '/admin/classify-tasks');
		expect(result.redirect?.status).toBe(303);
		expect(result.redirect?.location).toBe('/login?redirectTo=%2Fadmin%2Fclassify-tasks');
	});
});
