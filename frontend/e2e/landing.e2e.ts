import { expect, test } from '@playwright/test';
import { apiLogin, createObservation, createStation } from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.

test('the landing recent-observations strip is server-rendered with cards + media links', async ({
	request
}) => {
	const token = await apiLogin(request);
	const station = await createStation(request, token, {
		latitude: 47.1,
		longitude: 8.2,
		is_private: false
	});
	// A late observed_at keeps this observation in the bounded "recent" slice.
	await createObservation(request, token, {
		station_id: station.id,
		object_name: 'landing/strip/photo.jpg',
		observed_at: '2026-06-30T23:59:00+00:00',
		confidence_score: 0.7,
		latitude: 47.1,
		longitude: 8.2
	});

	// Inspect the raw SSR HTML — the strip must be present without client JS.
	const res = await request.get('/');
	expect(res.status()).toBe(200);
	const html = await res.text();
	expect(html).toContain('data-testid="recent-observations"');
	expect(html).toContain('data-testid="observation-card"');
	// Each card links to an observation detail page and renders a /media thumbnail.
	expect(html).toMatch(/href="\/observations\/[0-9a-f-]+"/);
	expect(html).toContain('/media/');
});
