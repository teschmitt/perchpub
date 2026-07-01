import { expect, test } from '@playwright/test';
import { apiLogin, createObservation, createStation } from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.

test('observation detail SSR HTML carries Open Graph share-preview tags', async ({ request }) => {
	const token = await apiLogin(request);
	const station = await createStation(request, token, {
		latitude: 48.137,
		longitude: 11.575,
		is_private: false
	});
	const objectName = 'ab/cd/og-preview.jpg';
	const observation = await createObservation(request, token, {
		station_id: station.id,
		object_name: objectName,
		observed_at: '2026-06-30T09:30:00+00:00',
		confidence_score: 0.88,
		latitude: 48.137,
		longitude: 11.575
	});

	// Inspect the raw SSR HTML — the share card must be present without client JS.
	const res = await request.get(`/observations/${observation.id}`);
	expect(res.status()).toBe(200);
	const html = await res.text();

	expect(html).toContain('property="og:title"');
	expect(html).toContain('property="og:description"');
	expect(html).toContain('property="og:url"');
	expect(html).toContain('property="og:image"');
	expect(html).toContain('name="twitter:card"');
	// og:image is the ABSOLUTE /media URL for this observation's object key.
	expect(html).toMatch(/<meta property="og:image" content="https?:\/\/[^"]+\/media\//);
	expect(html).toContain(`/media/${objectName}`);
});

test('a missing observation renders a 404, not a server error', async ({ request }) => {
	const res = await request.get('/observations/00000000-0000-0000-0000-000000000000');
	expect(res.status()).toBe(404);
});
