import { expect, test } from '@playwright/test';

test('the public landing page is server-rendered', async ({ request }) => {
	// Fetch the raw initial HTML (no client JS run) — SSR content must already be
	// present, not an empty client-only shell.
	const res = await request.get('/');
	expect(res.status()).toBe(200);

	const html = await res.text();
	expect(html).toContain('data-testid="landing"');
	expect(html).toContain('PerchPub');
	expect(html).toContain('self-hosted bird-feeder observation server');
});

test('the footer exposes a Source link for AGPL section 13', async ({ request }) => {
	// AGPL section 13: users interacting over the network must be able to reach
	// the corresponding source. The footer "Source code" link satisfies this and
	// must be server-rendered (present in the initial HTML, not injected later).
	const res = await request.get('/');
	expect(res.status()).toBe(200);

	const html = await res.text();
	expect(html).toContain('data-testid="footer-source"');
	expect(html).toContain('https://codeberg.org/perchpub/perchpub');
});

test('the public zone is reachable anonymously without a redirect', async ({ page }) => {
	await page.goto('/');
	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByTestId('landing')).toBeVisible();
});
