import { expect, test } from '@playwright/test';
import { signupUser, uiLogin, uiLoginSuperuser, uniqueEmail } from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.

const PASSWORD = 'password1234';

test('a non-superuser cannot reach the ops panel (guard)', async ({ page, request }) => {
	const email = uniqueEmail('plain-ops');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	const res = await page.goto('/admin/ops');
	expect(res?.status()).toBe(404);
});

test('the ops panel reports backend health', async ({ page }) => {
	await uiLoginSuperuser(page);
	await page.goto('/admin/ops');
	// The test stack's backend is up, so the health-check resolves to healthy.
	await expect(page.getByTestId('health-status')).toHaveText(/Healthy/);
});

test('sending a test email surfaces the backend response or error', async ({ page }) => {
	await uiLoginSuperuser(page);
	await page.goto('/admin/ops');

	await page.getByTestId('test-email-input').fill('ops@example.com');
	await page.getByTestId('test-email-submit').click();

	// Whether email is configured (success message) or not (error detail), the panel
	// surfaces the backend's outcome rather than crashing.
	await expect(page.getByTestId('email-success').or(page.getByTestId('email-error'))).toBeVisible();
});
