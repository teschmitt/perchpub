import { expect, test } from '@playwright/test';
import {
	apiLogin,
	createUser,
	signupUser,
	uiLogin,
	uiLoginSuperuser,
	uniqueEmail
} from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.

const PASSWORD = 'password1234';

test('a non-superuser cannot reach the admin users page (guard)', async ({ page, request }) => {
	const email = uniqueEmail('plainuser');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	// requireSuperuser 404s a logged-in non-superuser before any GET /users/ runs.
	const res = await page.goto('/admin/users');
	expect(res?.status()).toBe(404);
	await expect(page.getByTestId('users-table')).toHaveCount(0);
});

test('a superuser sees the user list', async ({ page }) => {
	await uiLoginSuperuser(page);
	await page.goto('/admin/users');
	await expect(page.getByTestId('users-table')).toBeVisible();
	// The seeded superuser is themselves a row.
	await expect(page.getByTestId('user-row').first()).toBeVisible();
});

test('creating a duplicate-email user surfaces the backend error', async ({ page, request }) => {
	const token = await apiLogin(request);
	const email = uniqueEmail('dupe');
	await createUser(request, token, { email, password: PASSWORD });

	await uiLoginSuperuser(page);
	await page.goto('/admin/users');
	await page.getByTestId('create-email').fill(email);
	await page.getByTestId('create-password').fill(PASSWORD);
	await page.getByTestId('create-submit').click();

	await expect(page.getByTestId('create-error')).toBeVisible();
	await expect(page.getByTestId('create-error')).toContainText('already exists');
});

test('a superuser edits a user and the is_active / is_superuser toggles persist', async ({
	page,
	request
}) => {
	const token = await apiLogin(request);
	const email = uniqueEmail('togglee');
	const created = await createUser(request, token, {
		email,
		password: PASSWORD,
		is_active: true,
		is_superuser: false
	});

	await uiLoginSuperuser(page);
	await page.goto(`/admin/users/${created.id}`);

	// Deactivate and grant superuser.
	await page.getByTestId('edit-is-active').uncheck();
	await page.getByTestId('edit-is-superuser').check();
	await page.getByTestId('edit-submit').click();

	// Redirected back to the list; reload the edit form and confirm the saved state.
	await expect(page).toHaveURL(/\/admin\/users$/);
	await page.goto(`/admin/users/${created.id}`);
	await expect(page.getByTestId('edit-is-active')).not.toBeChecked();
	await expect(page.getByTestId('edit-is-superuser')).toBeChecked();
});
