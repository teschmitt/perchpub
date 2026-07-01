import { expect, test } from '@playwright/test';
import { signupUser, uiLogin, uiLoginSuperuser, uniqueEmail } from './helpers';

const PASSWORD = 'password1234';

test('a user updates their profile name', async ({ page, request }) => {
	const email = uniqueEmail('profile');
	await signupUser(request, email, PASSWORD, 'Before Name');
	await uiLogin(page, email, PASSWORD);

	await page.goto('/account');
	await page.getByTestId('full-name-input').fill('After Name');
	await page.getByTestId('save-profile').click();

	await expect(page.getByTestId('profile-success')).toBeVisible();
	await expect(page.getByTestId('full-name-input')).toHaveValue('After Name');
});

test('a user changes their password and can log in with the new one', async ({ page, request }) => {
	const email = uniqueEmail('pwchange');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	const newPassword = 'brandnewpassword';
	await page.goto('/account');
	await page.getByTestId('current-password-input').fill(PASSWORD);
	await page.getByTestId('new-password-input').fill(newPassword);
	await page.getByTestId('save-password').click();
	await expect(page.getByTestId('password-success')).toBeVisible();

	// Verify the new password actually works end-to-end.
	await page.getByTestId('logout').click();
	await uiLogin(page, email, newPassword);
	await expect(page).toHaveURL(/\/dashboard$/);
});

test('a non-superuser deletes their account and is returned to the public landing', async ({
	page,
	request
}) => {
	const email = uniqueEmail('deleteme');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	await page.goto('/account');
	await page.getByTestId('confirm-delete').check();
	await page.getByTestId('delete-account').click();

	// Landed on the public landing with the session cleared.
	await expect(page).toHaveURL('/');
	// The (app) zone is no longer reachable — the guard bounces to login.
	await page.goto('/account');
	await expect(page).toHaveURL(/\/login/);
});

test('a superuser sees the delete control disabled and explained', async ({ page }) => {
	// Read-only: log in as the seeded superuser and view /account WITHOUT submitting
	// delete — never mutates the shared superuser account.
	await uiLoginSuperuser(page);
	await page.goto('/account');
	await expect(page.getByTestId('delete-disabled')).toBeVisible();
	await expect(page.getByTestId('delete-account')).toBeDisabled();
});
