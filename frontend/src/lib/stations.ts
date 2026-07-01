import type { components } from '$lib/api/schema';

type StationPublic = components['schemas']['StationPublic'];

/** Coordinate bounds mirroring the backend `StationBase` field constraints. */
export const LAT_MIN = -90;
export const LAT_MAX = 90;
export const LON_MIN = -180;
export const LON_MAX = 180;

export interface StationFormValues {
	latitude: string;
	longitude: string;
	is_private: boolean;
}

export interface StationFieldErrors {
	latitude?: string;
	longitude?: string;
}

export type StationFormResult =
	| { ok: true; value: { latitude: number; longitude: number; is_private: boolean } }
	| { ok: false; errors: StationFieldErrors; values: StationFormValues };

function parseCoordinate(
	raw: string,
	min: number,
	max: number,
	label: string
): { value: number } | { error: string } {
	const trimmed = raw.trim();
	if (trimmed === '') {
		return { error: `${label} is required.` };
	}
	const value = Number(trimmed);
	if (!Number.isFinite(value)) {
		return { error: `${label} must be a number.` };
	}
	if (value < min || value > max) {
		return { error: `${label} must be between ${min} and ${max}.` };
	}
	return { value };
}

/**
 * Parse and validate the shared station form (`latitude`, `longitude`,
 * `is_private`). Coordinates are bounded to `StationBase`'s ranges so an
 * out-of-range value is a typed field error the form re-renders with the raw
 * submitted values — the same body shape backs both create (`POST /station/`)
 * and the full-replacement edit (`PUT /station/{id}`).
 */
export function parseStationForm(form: FormData): StationFormResult {
	const latitude = String(form.get('latitude') ?? '');
	const longitude = String(form.get('longitude') ?? '');
	// An HTML checkbox submits its value only when checked, nothing when not.
	const is_private = form.get('is_private') != null;

	const errors: StationFieldErrors = {};
	const lat = parseCoordinate(latitude, LAT_MIN, LAT_MAX, 'Latitude');
	const lon = parseCoordinate(longitude, LON_MIN, LON_MAX, 'Longitude');
	if ('error' in lat) {
		errors.latitude = lat.error;
	}
	if ('error' in lon) {
		errors.longitude = lon.error;
	}

	if ('error' in lat || 'error' in lon) {
		return { ok: false, errors, values: { latitude, longitude, is_private } };
	}
	return {
		ok: true,
		value: {
			latitude: (lat as { value: number }).value,
			longitude: (lon as { value: number }).value,
			is_private
		}
	};
}

/** Whether a station is owned by the given user (the owner projection carries the id). */
export function isOwnStation(station: Pick<StationPublic, 'owner'>, userId: string): boolean {
	return station.owner?.id === userId;
}
