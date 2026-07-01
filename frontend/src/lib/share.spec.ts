import { describe, expect, it } from 'vitest';
import type { components } from '$lib/api/schema';
import { observationShareMeta } from './share';

type ObservationPublic = components['schemas']['ObservationPublic'];

const base: ObservationPublic = {
	id: '11111111-1111-1111-1111-111111111111',
	species: { id: 's1', scientific_name: 'Cyanistes caeruleus' },
	station: { id: 'st1', latitude: 51.5, longitude: -0.12, is_private: false, owner: null },
	observed_at: '2026-06-30T08:00:00+00:00',
	object_name: 'ab/cd/photo.jpg',
	confidence_score: 0.91,
	classification_result: null
};

describe('observationShareMeta', () => {
	it('builds an absolute og:image at the public /media URL', () => {
		const meta = observationShareMeta(base, 'https://perchpub.example');
		expect(meta.image).toBe('https://perchpub.example/media/ab/cd/photo.jpg');
	});

	it('builds an absolute canonical url for the observation', () => {
		const meta = observationShareMeta(base, 'https://perchpub.example/');
		expect(meta.url).toBe(
			'https://perchpub.example/observations/11111111-1111-1111-1111-111111111111'
		);
	});

	it('titles with the species and station', () => {
		const meta = observationShareMeta(base, 'https://perchpub.example');
		expect(meta.title).toContain('Cyanistes caeruleus');
		expect(meta.title).toContain('Station at 51.5000, -0.1200');
	});

	it('falls back to an unclassified title when no species is set', () => {
		const meta = observationShareMeta({ ...base, species: null }, 'https://perchpub.example');
		expect(meta.title).toContain('Unclassified');
	});
});
