import { expect, test } from '@playwright/test';
import { apiLoginAs, createStation, signupUser, uiLogin, uniqueEmail } from './helpers';

const PASSWORD = 'password1234';

test('an unauthenticated visit to the owner station list redirects to login', async ({ page }) => {
	await page.goto('/stations/mine');
	await expect(page).toHaveURL(/\/login\?redirectTo=%2Fstations%2Fmine$/);
	await expect(page.getByTestId('email-input')).toBeVisible();
});

test('an owner sees their station and a quiet secondary Add-station action to the setup wizard', async ({
	page,
	request
}) => {
	const email = uniqueEmail('stationowner');
	await signupUser(request, email, PASSWORD, 'Station Owner');
	// Station creation is unified into the enrollment wizard; the device-less
	// create UI is gone. Seed the owner's station through the retained backend
	// endpoint (kept for tooling/tests) so we can exercise the list surface.
	const token = await apiLoginAs(request, email, PASSWORD);
	await createStation(request, token, { latitude: 12.3456, longitude: 65.4321, is_private: false });

	await uiLogin(page, email, PASSWORD);
	await page.goto('/stations/mine');
	await expect(page.getByTestId('my-stations')).toContainText('12.3456, 65.4321');

	// "Add station" is a quiet secondary action routed to the setup wizard, and
	// there is no primary-styled "New station" button or device-less create form.
	const addStation = page.getByTestId('add-station');
	await expect(addStation).toHaveAttribute('href', '/stations/new');
	await expect(page.getByTestId('new-station')).toHaveCount(0);
});

test("an owner toggles a station's privacy from the edit form", async ({ page, request }) => {
	const email = uniqueEmail('editowner');
	await signupUser(request, email, PASSWORD);
	const token = await apiLoginAs(request, email, PASSWORD);
	await createStation(request, token, {
		latitude: 40.1234,
		longitude: -73.9876,
		is_private: false
	});

	await uiLogin(page, email, PASSWORD);
	await page.goto('/stations/mine');
	await expect(page.getByTestId('private-badge')).toHaveCount(0);

	// Open the edit form and toggle is_private on.
	await page.getByTestId('edit-station').first().click();
	await page.waitForURL(/\/stations\/[^/]+\/edit$/);
	await page.getByTestId('is-private-input').check();
	await page.getByTestId('submit').click();

	await page.waitForURL('**/stations/mine');
	await expect(page.getByTestId('private-badge')).toHaveCount(1);
});
