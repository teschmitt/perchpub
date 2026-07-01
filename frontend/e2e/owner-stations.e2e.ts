import { expect, test } from '@playwright/test';
import { signupUser, uiLogin, uniqueEmail } from './helpers';

const PASSWORD = 'password1234';

test('an unauthenticated visit to the owner station list redirects to login', async ({ page }) => {
	await page.goto('/stations/mine');
	await expect(page).toHaveURL(/\/login\?redirectTo=%2Fstations%2Fmine$/);
	await expect(page.getByTestId('email-input')).toBeVisible();
});

test('an owner creates a station and sees it in their list', async ({ page, request }) => {
	const email = uniqueEmail('stationowner');
	await signupUser(request, email, PASSWORD, 'Station Owner');
	await uiLogin(page, email, PASSWORD);

	await page.goto('/stations/mine');
	await page.getByTestId('new-station').click();
	await page.waitForURL('**/stations/new');

	await page.getByTestId('latitude-input').fill('12.3456');
	await page.getByTestId('longitude-input').fill('65.4321');
	await page.getByTestId('submit').click();

	await page.waitForURL('**/stations/mine');
	await expect(page.getByTestId('my-stations')).toContainText('12.3456, 65.4321');
});

test("an owner toggles a station's privacy from the edit form", async ({ page, request }) => {
	const email = uniqueEmail('editowner');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	// Create a public station via the UI.
	await page.goto('/stations/new');
	await page.getByTestId('latitude-input').fill('40.1234');
	await page.getByTestId('longitude-input').fill('-73.9876');
	await page.getByTestId('submit').click();
	await page.waitForURL('**/stations/mine');
	await expect(page.getByTestId('private-badge')).toHaveCount(0);

	// Open the edit form and toggle is_private on.
	await page.getByTestId('edit-station').first().click();
	await page.waitForURL(/\/stations\/[^/]+\/edit$/);
	await page.getByTestId('is-private-input').check();
	await page.getByTestId('submit').click();

	await page.waitForURL('**/stations/mine');
	await expect(page.getByTestId('private-badge')).toHaveCount(1);
});
