import { expect, test } from '@playwright/test';
import { uiLoginSuperuser, uniqueEmail } from './helpers';

test('an anonymous visitor signs up and sees the generic confirmation', async ({ page }) => {
	await page.goto('/login');
	await page.getByTestId('signup-link').click();
	await page.waitForURL('**/signup');

	await page.getByTestId('email-input').fill(uniqueEmail('signup'));
	await page.getByTestId('password-input').fill('password1234');
	await page.getByTestId('submit').click();

	// The UI shows the backend's generic message and never asserts an account was
	// created (no account enumeration).
	await expect(page.getByTestId('signup-confirmation')).toBeVisible();
	await expect(page.getByTestId('signup-form')).toHaveCount(0);
});

test('an already-logged-in user is redirected away from signup', async ({ page }) => {
	await uiLoginSuperuser(page);
	await page.goto('/signup');
	await expect(page).toHaveURL(/\/dashboard$/);
});
