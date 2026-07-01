import { expect, test } from '@playwright/test';
import { signupUser, uiLogin, uiLoginSuperuser, uniqueEmail } from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.
//
// NOTE: classify tasks are created only by the upload + worker pipeline (there is
// no POST /classify-task/ endpoint), so these e2e cannot seed rows. Row rendering
// and the status→label mapping are covered by the unit tests (classify.spec.ts,
// classify-tasks-load.spec.ts). Here we verify the guard, that the page renders,
// and that the status filter round-trips through the URL into the load.

const PASSWORD = 'password1234';

test('a non-superuser cannot reach the admin classify-task list (guard)', async ({
	page,
	request
}) => {
	const email = uniqueEmail('plain-ct');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	const res = await page.goto('/admin/classify-tasks');
	expect(res?.status()).toBe(404);
	await expect(page.getByTestId('classify-filters')).toHaveCount(0);
});

test('a superuser can open the list and apply the status filter via the URL', async ({ page }) => {
	await uiLoginSuperuser(page);
	await page.goto('/admin/classify-tasks');
	await expect(page.getByTestId('classify-filters')).toBeVisible();

	await page.getByTestId('filter-status').selectOption('Failed');
	await page.getByTestId('filter-apply').click();

	// The GET form navigates with the filter in the URL, which the load reads back.
	await expect(page).toHaveURL(/[?&]status=Failed\b/);
	await expect(page.getByTestId('filter-status')).toHaveValue('Failed');
});
