import type { components } from '$lib/api/schema';
import type { StationFieldErrors } from '$lib/stations';

type StationPublic = components['schemas']['StationPublic'];

/** The one-time enrollment session as returned by `POST /enrollment/create`. */
export interface EnrollSession {
	session_id: string;
	auth_token: string;
	expires_at: string;
}

/**
 * Unified result shape for both enroll form actions (`create` + `check`), kept as
 * one interface so the page's `ActionData` is a single type. `session` carries the
 * one-time token surfaced ONCE by `create`; `baseline` is the operator's station
 * ids at session start, threaded back to `check` so it can diff for a new row.
 */
export interface EnrollResult {
	intent: 'create' | 'check';
	session?: EnrollSession;
	baseline?: string[];
	/** `check`: id of a newly enrolled station, or null when none appeared. */
	newStationId?: string | null;
	errors?: StationFieldErrors;
	values?: { latitude: string; longitude: string };
	formError?: string;
}

/** Enrollment session TTL in seconds — mirrors the backend `TTL_SECONDS`. */
export const ENROLLMENT_TTL_SECONDS = 300;

/**
 * Whole seconds remaining until `expiresAt` (ISO date-time), clamped at zero.
 * `now` is epoch milliseconds (pass `Date.now()` from the browser). An
 * unparseable timestamp yields `0` rather than propagating `NaN`.
 */
export function secondsRemaining(expiresAt: string, now: number): number {
	const deadline = Date.parse(expiresAt);
	if (Number.isNaN(deadline)) {
		return 0;
	}
	return Math.max(0, Math.ceil((deadline - now) / 1000));
}

/** True once the countdown to `expiresAt` has reached the deadline. */
export function isExpired(expiresAt: string, now: number): boolean {
	return secondsRemaining(expiresAt, now) <= 0;
}

/** Format a remaining-seconds value as `m:ss`, never negative. */
export function formatCountdown(seconds: number): string {
	const total = Math.max(0, Math.floor(seconds));
	const minutes = Math.floor(total / 60);
	const rest = total % 60;
	return `${minutes}:${rest.toString().padStart(2, '0')}`;
}

/**
 * The id of a newly enrolled station: the first station owned by `userId` whose
 * id was NOT present in `baseline` (the owner's station ids captured when the
 * enrollment session was created). Returns `null` when none has appeared yet —
 * there is no operator-facing poll endpoint, so the wizard diffs the list.
 */
export function findNewStationId(
	baseline: string[],
	stations: Array<Pick<StationPublic, 'id' | 'owner'>>,
	userId: string
): string | null {
	const seen = new Set(baseline);
	for (const station of stations) {
		if (station.owner?.id === userId && !seen.has(station.id)) {
			return station.id;
		}
	}
	return null;
}
