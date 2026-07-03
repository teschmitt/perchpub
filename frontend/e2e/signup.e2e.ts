import { expect, test } from '@playwright/test';
import { signupUser, uiLoginSuperuser, uniqueEmail } from './helpers';

const PASSWORD = 'password1234';

test('a new visitor signs up, is auto-logged-in, and lands on first-station setup', async ({
	page,
	context
}) => {
	await page.goto('/login');
	await page.getByTestId('signup-link').click();
	await page.waitForURL('**/signup');

	await page.getByTestId('email-input').fill(uniqueEmail('signup'));
	await page.getByTestId('password-input').fill(PASSWORD);
	await page.getByTestId('submit').click();

	// Auto-login hands the freshly-created account straight into first-station setup.
	await page.waitForURL('**/stations/new');
	await expect(page.getByTestId('enroll-form')).toBeVisible();

	// A BFF session cookie was set (the JWT never reaches client JS).
	const cookies = await context.cookies();
	expect(cookies.find((c) => c.name === 'pp_session')?.value).toBeTruthy();
});

test('signing up an existing email with a wrong password falls back to login (no enumeration)', async ({
	page,
	request
}) => {
	// Pre-register the account, then attempt to "sign up" it again with a different
	// password: signup is a backend no-op, the follow-up grant fails, and the action
	// falls back to the login form — indistinguishable from a mistyped password.
	const email = uniqueEmail('taken');
	await signupUser(request, email, PASSWORD);

	await page.goto('/signup');
	await page.getByTestId('email-input').fill(email);
	await page.getByTestId('password-input').fill('a-different-password');
	await page.getByTestId('submit').click();

	await page.waitForURL('**/login');
	await expect(page.getByTestId('email-input')).toBeVisible();

	// No session was established.
	const cookies = await page.context().cookies();
	expect(cookies.find((c) => c.name === 'pp_session')?.value).toBeFalsy();
});

test('an already-logged-in user is redirected away from signup', async ({ page }) => {
	await uiLoginSuperuser(page);
	await page.goto('/signup');
	await expect(page).toHaveURL(/\/dashboard$/);
});
