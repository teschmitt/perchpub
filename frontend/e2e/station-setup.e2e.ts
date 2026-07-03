import { expect, test } from '@playwright/test';
import { apiLoginAs, createStation, signupUser, uiLogin, uniqueEmail } from './helpers';

const PASSWORD = 'password1234';

test('the setup wizard lives at /stations/new and the legacy /enroll redirects to it', async ({
	page,
	request
}) => {
	const email = uniqueEmail('router');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	// /stations/new serves the enrollment setup wizard (coordinates + privacy),
	// NOT a device-less create form.
	await page.goto('/stations/new');
	await expect(page.getByTestId('enroll-form')).toBeVisible();
	await expect(page.getByTestId('is-private-input')).toBeVisible();
	await expect(page.getByTestId('start-enrollment')).toBeVisible();

	// The legacy /enroll route redirects to /stations/new.
	await page.goto('/enroll');
	await expect(page).toHaveURL(/\/stations\/new$/);
	await expect(page.getByTestId('enroll-form')).toBeVisible();
});

test('the app sidebar has no standalone Enroll-device destination', async ({ page, request }) => {
	const email = uniqueEmail('navcheck');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);
	await page.goto('/dashboard');

	// Primary nav: Dashboard, My stations, Account — and no "Enroll device" item.
	await expect(page.getByTestId('nav-stations')).toBeVisible();
	await expect(page.getByTestId('nav-account')).toBeVisible();
	await expect(page.getByTestId('nav-enroll')).toHaveCount(0);
});

test('a zero-station user sees the first-station hero, and "do it later" returns to it', async ({
	page,
	request
}) => {
	const email = uniqueEmail('onboard');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	// The dashboard leads with the onboarding hero when the user owns no stations.
	await page.goto('/dashboard');
	await expect(page.getByTestId('onboarding-hero')).toBeVisible();
	await page.getByTestId('setup-first-station').click();
	await page.waitForURL('**/stations/new');

	// "Do it later" leaves setup, creates no station, and returns to the dashboard,
	// which still recommends first-station setup.
	await page.getByTestId('defer-setup').click();
	await page.waitForURL('**/dashboard');
	await expect(page.getByTestId('onboarding-hero')).toBeVisible();
});

test('privacy is chosen at setup, and a private station shows as Private in the list', async ({
	page,
	request
}) => {
	const email = uniqueEmail('privsetup');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	// The setup wizard lets the operator choose privacy up front; starting the
	// session persists that choice (it is applied to the Station when the Pi
	// confirms — the device side is out of browser scope, covered by the backend
	// enrollment test `test_confirm_private_session_yields_private_station`).
	await page.goto('/stations/new');
	await page.getByTestId('latitude-input').fill('48.8566');
	await page.getByTestId('longitude-input').fill('2.3522');
	await page.getByTestId('is-private-input').check();
	await page.getByTestId('start-enrollment').click();
	await expect(page.getByTestId('enroll-token')).toBeVisible();

	// A private station (as produced by a private-at-setup enrollment) renders with
	// the Private badge in the owner's list.
	const token = await apiLoginAs(request, email, PASSWORD);
	await createStation(request, token, { latitude: 48.8566, longitude: 2.3522, is_private: true });
	await page.goto('/stations/mine');
	await expect(page.getByTestId('private-badge')).toHaveCount(1);
});
