import { expect, test } from '@playwright/test';
import { apiLogin, createSpecies } from './helpers';

// Requires a reachable backend (INTERNAL_API_URL) with the seeded superuser.

test('the species catalog lists a seeded species (from the {data,count} wrapper) and links to detail', async ({
	request
}) => {
	const token = await apiLogin(request);
	const name = 'Erithacus rubecula';
	const species = await createSpecies(request, token, {
		scientific_name: name,
		classification_id: 990001
	});

	const list = await request.get('/species');
	expect(list.status()).toBe(200);
	const listHtml = await list.text();
	expect(listHtml).toContain('data-testid="species-list"');
	expect(listHtml).toContain(name);
	expect(listHtml).toContain(`/species/${species.id}`);

	const detail = await request.get(`/species/${species.id}`);
	expect(detail.status()).toBe(200);
	const detailHtml = await detail.text();
	expect(detailHtml).toContain('data-testid="species-name"');
	expect(detailHtml).toContain(name);
});

test('a missing species renders not-found (404)', async ({ request }) => {
	const res = await request.get('/species/00000000-0000-0000-0000-000000000000');
	expect(res.status()).toBe(404);
});
