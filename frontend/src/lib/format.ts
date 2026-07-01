import type { components } from '$lib/api/schema';

type StationPublic = components['schemas']['StationPublic'];

/**
 * Format a 0–1 AI confidence score as a whole-percent string, or `null` when
 * there is no score (so the caller can hide the field). A genuine `0` score is
 * kept ("0%"), not treated as missing.
 */
export function formatConfidence(score: number | null | undefined): string | null {
	if (score === null || score === undefined) {
		return null;
	}
	return `${Math.round(score * 100)}%`;
}

/**
 * Render the stable calendar date (`YYYY-MM-DD`) from an ISO date-time. Slicing
 * the string rather than going through `Date`/`Intl` keeps SSR and client output
 * byte-identical, avoiding a hydration mismatch from differing locales.
 */
export function formatDate(iso: string): string {
	return iso.slice(0, 10);
}

/**
 * Display label for a station. `StationPublic` has no name field, so prefer the
 * owner's full name and fall back to the station's coordinates.
 */
export function stationLabel(
	station: Pick<StationPublic, 'latitude' | 'longitude' | 'owner'>
): string {
	if (station.owner?.full_name) {
		return station.owner.full_name;
	}
	return `Station at ${station.latitude.toFixed(4)}, ${station.longitude.toFixed(4)}`;
}
