import { expect, test } from '@playwright/test';
import { signupUser, uiLogin, uniqueEmail } from './helpers';

const PASSWORD = 'password1234';

test('the enroll wizard presents the pairing QR with a manual fallback and a running countdown', async ({
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

	// The token panel appears with the scannable QR as the primary artifact.
	await expect(page.getByTestId('enroll-token')).toBeVisible();
	await expect(page.getByTestId('enroll-qr').locator('svg')).toBeVisible();

	// The copyable session id and one-time token remain as a manual fallback.
	await page.getByTestId('enroll-manual-toggle').click();
	await expect(page.getByTestId('auth-token')).not.toBeEmpty();
	await expect(page.getByTestId('session-id')).not.toBeEmpty();
	await expect(page.getByTestId('copy-token')).toBeVisible();
	await expect(page.getByTestId('copy-session')).toBeVisible();

	// The countdown is running (mm:ss) and ticks down within the TTL.
	const countdown = page.getByTestId('countdown');
	await expect(countdown).toHaveText(/^\d:\d\d$/);
	const first = await countdown.textContent();
	await page.waitForTimeout(1100);
	const second = await countdown.textContent();
	expect(second).not.toBe(first);

	// The actual one-time token value must never leak into the URL, a query
	// string, or a persisted client store.
	const tokenValue = ((await page.getByTestId('auth-token').textContent()) ?? '').trim();
	expect(tokenValue.length).toBeGreaterThan(0);
	expect(page.url()).not.toContain(tokenValue);
	const stores = await page.evaluate(
		() => JSON.stringify(localStorage) + JSON.stringify(sessionStorage)
	);
	expect(stores).not.toContain(tokenValue);

	// "Check" before the device confirms reports no station yet (no poll endpoint).
	await page.getByTestId('check-station').click();
	await expect(page.getByTestId('check-pending')).toBeVisible();

	// Navigating away and back does NOT re-display the one-time credential.
	await page.goto('/');
	await page.goto('/enroll');
	await expect(page.getByTestId('enroll-token')).toHaveCount(0);
	await expect(page.getByTestId('enroll-form')).toBeVisible();
});

test('the pairing QR and token expire visibly once the countdown reaches zero', async ({
	page,
	request
}) => {
	const email = uniqueEmail('expirer');
	await signupUser(request, email, PASSWORD);
	await uiLogin(page, email, PASSWORD);

	// Fake the browser clock so we can jump past the TTL without waiting it out.
	await page.clock.install();
	await page.goto('/enroll');
	await page.getByTestId('latitude-input').fill('10.0000');
	await page.getByTestId('longitude-input').fill('20.0000');
	await page.getByTestId('start-enrollment').click();
	await expect(page.getByTestId('enroll-token')).toBeVisible();
	await expect(page.getByTestId('enroll-qr')).toBeVisible();

	// Advance well past the TTL (generous margin over any client/server skew): the
	// wizard marks the credential expired and stops offering the QR and token.
	await page.clock.fastForward('10:00');
	await expect(page.getByTestId('token-expired')).toBeVisible();
	await expect(page.getByTestId('enroll-qr')).toHaveCount(0);
	await expect(page.getByTestId('enroll-qr-expired')).toBeVisible();

	await page.getByTestId('enroll-manual-toggle').click();
	await expect(page.getByTestId('copy-token')).toBeDisabled();
});
