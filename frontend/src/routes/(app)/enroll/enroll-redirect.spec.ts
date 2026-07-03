import { isRedirect } from '@sveltejs/kit';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/private', () => ({ env: {} }));

const { load } = await import('./+page.server');

describe('legacy /enroll route', () => {
	it('permanently (308) redirects to the setup wizard at /stations/new', async () => {
		// Station creation and device enrollment are unified at /stations/new; the
		// old /enroll wizard URL redirects so existing bookmarks/links keep working.
		let redirected: { status: number; location: string } | undefined;
		try {
			await load({} as unknown as Parameters<typeof load>[0]);
		} catch (e) {
			if (isRedirect(e)) {
				redirected = { status: e.status, location: e.location };
			} else {
				throw e;
			}
		}
		expect(redirected?.status).toBe(308);
		expect(redirected?.location).toBe('/stations/new');
	});
});
