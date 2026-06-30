import { expect, test } from '@playwright/test';

// Credentials come from the environment (the compose `playwright` service loads
// .env.dev, which carries the seeded FIRST_SUPERUSER). Requires a reachable
// backend at INTERNAL_API_URL.
const EMAIL = process.env.FIRST_SUPERUSER ?? 'admin@example.com';
const PASSWORD = process.env.FIRST_SUPERUSER_PASSWORD ?? 'changethis';

test('login establishes an httpOnly session cookie and redirects', async ({ page, context }) => {
	// A hostile redirectTo must NOT be honored (open-redirect / CWE-601): login
	// lands on the safe default, not the off-origin host.
	await page.goto('/login?redirectTo=//evil.example');
	await page.getByTestId('email-input').fill(EMAIL);
	await page.getByTestId('password-input').fill(PASSWORD);
	await page.getByRole('button', { name: 'Log In' }).click();

	await page.waitForURL('**/dashboard');
	expect(new URL(page.url()).hostname).toBe('localhost');

	const session = (await context.cookies()).find((c) => c.name === 'pp_session');
	expect(session, 'pp_session cookie is set').toBeTruthy();
	expect(session?.httpOnly, 'pp_session is httpOnly').toBe(true);

	// The JWT is never exposed to client-side JavaScript.
	const clientCookies = await page.evaluate(() => document.cookie);
	expect(clientCookies).not.toContain('pp_session');
});
