import { expect, test } from '@playwright/test';
import {
	apiLogin,
	createObservation,
	createSpecies,
	createStation,
	uiLoginSuperuser
} from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.

async function seedUnclassifiedObservation(request: import('@playwright/test').APIRequestContext) {
	const token = await apiLogin(request);
	const station = await createStation(request, token, {
		latitude: 48.1,
		longitude: 11.5,
		is_private: false
	});
	const observation = await createObservation(request, token, {
		station_id: station.id,
		object_name: 'ab/cd/reclassify.jpg',
		observed_at: '2026-06-30T09:30:00+00:00',
		confidence_score: 0.42,
		latitude: 48.1,
		longitude: 11.5,
		species_id: null
	});
	return { token, observation };
}

test('the reclassify control is hidden from anonymous visitors', async ({ page, request }) => {
	const { observation } = await seedUnclassifiedObservation(request);
	await page.goto(`/observations/${observation.id}`);
	await expect(page.getByTestId('reclassify')).toHaveCount(0);
});

test('a superuser reclassifies the observation and sees the corrected species + indicator', async ({
	page,
	request
}) => {
	const { token, observation } = await seedUnclassifiedObservation(request);
	// A distinctly-named species so the assertion is unambiguous.
	const species = await createSpecies(request, token, {
		scientific_name: `Corvus test ${Date.now()}`,
		classification_id: Math.floor(Math.random() * 1e9)
	});

	await uiLoginSuperuser(page);
	await page.goto(`/observations/${observation.id}`);
	await expect(page.getByTestId('reclassify')).toBeVisible();

	await page.getByTestId('reclassify-species').selectOption(species.id);
	await page.getByTestId('reclassify-submit').click();

	// The success signal for the "manually classified" indicator is the action result.
	await expect(page.getByTestId('manually-classified')).toBeVisible();
	// The re-run load reflects the corrected species on the page.
	await expect(page.getByTestId('species-link')).toContainText(species.scientific_name);
});
