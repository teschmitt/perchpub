import { describe, expect, it } from 'vitest';
import { formatConfidence, formatDate, stationLabel } from './format';

describe('formatDate', () => {
	it('renders the stable calendar date from an ISO date-time (no locale drift)', () => {
		// Slicing the ISO string keeps SSR and client output identical (no
		// hydration mismatch from differing locales/timezones).
		expect(formatDate('2026-06-30T14:25:00+00:00')).toBe('2026-06-30');
	});
});

describe('formatConfidence', () => {
	it('formats a 0-1 score as a whole percentage', () => {
		expect(formatConfidence(0.873)).toBe('87%');
		expect(formatConfidence(1)).toBe('100%');
	});

	it('keeps a genuine zero score rather than hiding it', () => {
		expect(formatConfidence(0)).toBe('0%');
	});

	it('returns null when there is no score', () => {
		expect(formatConfidence(null)).toBeNull();
	});
});

describe('stationLabel', () => {
	it("uses the owner's full name when present", () => {
		expect(
			stationLabel({ latitude: 40.7128, longitude: -74.006, owner: { id: 'x', full_name: 'Ada' } })
		).toBe('Ada');
	});

	it('falls back to coordinates when the station has no named owner', () => {
		expect(stationLabel({ latitude: 40.7128, longitude: -74.006, owner: null })).toBe(
			'Station at 40.7128, -74.0060'
		);
		expect(stationLabel({ latitude: 1, longitude: 2, owner: { id: 'x', full_name: null } })).toBe(
			'Station at 1.0000, 2.0000'
		);
	});
});
