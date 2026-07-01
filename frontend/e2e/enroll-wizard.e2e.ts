import { expect, test } from '@playwright/test';
import { signupUser, uiLogin, uniqueEmail } from './helpers';

const PASSWORD = 'password1234';

test('the enroll wizard presents the one-time token with a copy control and a running countdown', async ({
	page,
	request
}) => {
	const email = uniqueEmail('enroller');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	await page.goto('/enroll');
	await page.getByTestId('latitude-input').fill('51.5074');
	await page.getByTestId('longitude-input').fill('-0.1278');
	await page.getByTestId('start-enrollment').click();

	// The token panel appears with the one-time token, session id, and copy controls.
	await expect(page.getByTestId('enroll-token')).toBeVisible();
	await expect(page.getByTestId('auth-token')).not.toBeEmpty();
	await expect(page.getByTestId('session-id')).not.toBeEmpty();
	await expect(page.getByTestId('copy-token')).toBeVisible();
	await expect(page.getByTestId('copy-session')).toBeVisible();

	// The countdown is running (mm:ss) and ticks down within the 300s TTL.
	const countdown = page.getByTestId('countdown');
	await expect(countdown).toHaveText(/^\d:\d\d$/);
	const first = await countdown.textContent();
	await page.waitForTimeout(1100);
	const second = await countdown.textContent();
	expect(second).not.toBe(first);

	// The one-time token must never appear in the URL or a query string.
	expect(page.url()).not.toContain('auth');

	// "Check" before the device confirms reports no station yet (no poll endpoint).
	await page.getByTestId('check-station').click();
	await expect(page.getByTestId('check-pending')).toBeVisible();
});

test('the one-time token expires visibly once the 300s countdown reaches zero', async ({
	page,
	request
}) => {
	const email = uniqueEmail('expirer');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	// Fake the browser clock so we can jump past the TTL without waiting 5 minutes.
	await page.clock.install();
	await page.goto('/enroll');
	await page.getByTestId('latitude-input').fill('10.0000');
	await page.getByTestId('longitude-input').fill('20.0000');
	await page.getByTestId('start-enrollment').click();
	await expect(page.getByTestId('enroll-token')).toBeVisible();
	await expect(page.getByTestId('copy-token')).toBeEnabled();

	// Advance well past the 300s TTL (generous margin over any client/server skew):
	// the wizard marks the token expired and stops offering it as usable.
	await page.clock.fastForward('10:00');
	await expect(page.getByTestId('token-expired')).toBeVisible();
	await expect(page.getByTestId('copy-token')).toBeDisabled();
});
