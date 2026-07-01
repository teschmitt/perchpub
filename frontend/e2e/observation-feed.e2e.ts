import { expect, test } from '@playwright/test';
import { apiLogin, createObservation, createStation } from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.

const PAGE_SIZE = 24; // mirrors DEFAULT_LIMIT in src/lib/pagination.ts

function cardCount(html: string): number {
	return (html.match(/data-testid="observation-card"/g) ?? []).length;
}

test('the feed paginates: the next control advances skip to the second page', async ({
	request
}) => {
	const token = await apiLogin(request);
	const station = await createStation(request, token, {
		latitude: 50.0,
		longitude: 8.0,
		is_private: false
	});

	// One more than a full page guarantees a second page exists.
	for (let i = 0; i < PAGE_SIZE + 1; i++) {
		const day = String((i % 27) + 1).padStart(2, '0');
		await createObservation(request, token, {
			station_id: station.id,
			object_name: `feed/${i}/clip.jpg`,
			observed_at: `2026-05-${day}T12:00:00+00:00`,
			confidence_score: 0.5,
			latitude: 50.0,
			longitude: 8.0
		});
	}

	// Page 1 fills to the limit and offers a next link to page 2.
	const page1 = await request.get('/observations');
	expect(page1.status()).toBe(200);
	const html1 = await page1.text();
	expect(cardCount(html1)).toBe(PAGE_SIZE);
	expect(html1).toMatch(/data-testid="page-next"[^>]*href="[^"]*page=2/);

	// Each card surfaces its media thumbnail, species (Unclassified — seeded with
	// no species_id), and confidence score (0.5 → 50%).
	expect(html1).toContain('/media/feed/');
	expect(html1).toContain('Unclassified');
	expect(html1).toContain('data-testid="confidence"');
	expect(html1).toContain('50%');

	// Following to page 2 advances the window (skip += limit) and enables prev.
	const page2 = await request.get('/observations?page=2');
	expect(page2.status()).toBe(200);
	const html2 = await page2.text();
	expect(cardCount(html2)).toBeGreaterThanOrEqual(1);
	expect(html2).toMatch(/data-testid="page-prev"[^>]*href="[^"]*page=1/);
});

test('an out-of-range page renders an empty slice, not an error', async ({ request }) => {
	// A very high page is past the end → empty grid, next disabled, no error.
	const res = await request.get('/observations?page=100000');
	expect(res.status()).toBe(200);
	const html = await res.text();
	expect(cardCount(html)).toBe(0);
	expect(html).toContain('data-testid="observations-empty"');
	expect(html).toMatch(/data-testid="page-next"[^>]*aria-disabled="true"/);
});
