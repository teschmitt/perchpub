import { expect, test, type Browser } from '@playwright/test';
import { apiLogin, createStation } from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.

const EMAIL = process.env.FIRST_SUPERUSER ?? 'admin@example.com';
const PASSWORD = process.env.FIRST_SUPERUSER_PASSWORD ?? 'changethis';

// Stations have no name field, so distinctive coordinates are the markers.
const PUBLIC_MARKER = '13.1313, 64.6464';
const PRIVATE_MARKER = '37.3737, -42.4242';

/** A fresh context logged in as the owner (the seeded superuser). */
async function loginOwner(browser: Browser) {
	const context = await browser.newContext();
	const page = await context.newPage();
	await page.goto('/login');
	await page.getByTestId('email-input').fill(EMAIL);
	await page.getByTestId('password-input').fill(PASSWORD);
	await page.getByRole('button', { name: 'Log In' }).click();
	await page.waitForURL('**/dashboard');
	return { context, page };
}

test('stations list: an anonymous visitor sees public stations but not private ones (view-only)', async ({
	browser,
	request
}) => {
	const token = await apiLogin(request);
	await createStation(request, token, { latitude: 13.1313, longitude: 64.6464, is_private: false });
	await createStation(request, token, {
		latitude: 37.3737,
		longitude: -42.4242,
		is_private: true
	});

	const anon = await browser.newContext();
	const anonPage = await anon.newPage();
	await anonPage.goto('/stations');
	const html = await anonPage.content();
	expect(html).toContain(PUBLIC_MARKER);
	expect(html).not.toContain(PRIVATE_MARKER);
	// View-only: no create/edit affordances (no management routes or forms).
	expect(html).not.toContain('/stations/new');
	expect(html).not.toMatch(/\/stations\/[^"]+\/edit/);
	expect(html).not.toContain('<form');
	await anon.close();
});

test('a private station: 404 for anonymous (no existence leak); its detail renders for the owner', async ({
	browser,
	request
}) => {
	const token = await apiLogin(request);
	const priv = await createStation(request, token, {
		latitude: 22.2222,
		longitude: -11.1111,
		is_private: true
	});

	// Anonymous → not found (must not disclose that the station exists).
	const anon = await browser.newContext();
	const anonPage = await anon.newPage();
	const anonResp = await anonPage.goto(`/stations/${priv.id}`);
	expect(anonResp?.status()).toBe(404);
	await anon.close();

	// Owner → the private station's detail renders. Uses the detail route, so the
	// assertion is independent of how many stations the owner can see (no paging).
	const { context, page } = await loginOwner(browser);
	const ownerResp = await page.goto(`/stations/${priv.id}`);
	expect(ownerResp?.status()).toBe(200);
	const ownerHtml = await page.content();
	expect(ownerHtml).toContain('22.2222, -11.1111');
	expect(ownerHtml).toContain('Private');
	await context.close();
});

test('a visible public station renders its detail (location, owner, visibility), view-only', async ({
	browser,
	request
}) => {
	const token = await apiLogin(request);
	const pub = await createStation(request, token, {
		latitude: 55.5001,
		longitude: 9.9002,
		is_private: false
	});

	const anon = await browser.newContext();
	const anonPage = await anon.newPage();
	const resp = await anonPage.goto(`/stations/${pub.id}`);
	expect(resp?.status()).toBe(200);
	const html = await anonPage.content();
	expect(html).toContain('data-testid="station-name"');
	expect(html).toContain('55.5001, 9.9002'); // location
	expect(html).toContain('Owner'); // owner row label
	expect(html).toContain('Public'); // visibility
	// View-only: no management controls (no edit/delete routes or mutation forms).
	expect(html).not.toMatch(/\/stations\/[^"]+\/edit/);
	expect(html).not.toContain('<form');
	await anon.close();
});
