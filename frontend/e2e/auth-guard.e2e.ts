import { expect, test } from '@playwright/test';

test('unauthenticated access to the authed zone redirects to login', async ({ page }) => {
	await page.goto('/dashboard');
	// The (app) guard redirects to /login before any protected content renders,
	// carrying where the user was headed.
	await expect(page).toHaveURL(/\/login\?redirectTo=%2Fdashboard$/);
	await expect(page.getByTestId('email-input')).toBeVisible();
});
