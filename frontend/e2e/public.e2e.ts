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

test('the public zone is reachable anonymously without a redirect', async ({ page }) => {
	await page.goto('/');
	await expect(page).toHaveURL(/\/$/);
	await expect(page.getByTestId('landing')).toBeVisible();
});
