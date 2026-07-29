import type { components } from '$lib/api/schema';
import type { StationFieldErrors } from '$lib/stations';

type StationPublic = components['schemas']['StationPublic'];

/** The one-time enrollment session as returned by `POST /enrollment/create`. */
export interface EnrollSession {
	session_id: string;
	auth_token: string;
	/** Device-CA root SPKI pin (64-hex) the station verifies `/confirm`'s chain against. */
	ca_pin: string;
	/**
	 * Public station-facing enrollment origin (the `:443` edge, e.g.
	 * `https://api.perchpub.net`) the station talks to and derives its `:8443`
	 * upload endpoint from. Sourced from the backend `STATION_EDGE_URL` so a
	 * station enrolls with zero pre-configuration.
	 */
	perchpub_url: string;
	expires_at: string;
}

/**
 * The compact JSON the enrollment QR encodes — the four perchstation
 * pairing-contract fields (`session_id`, `auth_token`, `ca_pin`, `perchpub_url`),
 * with the original three in contract order, as one byte-mode symbol.
 * `perchpub_url` is the `:443` enrollment origin the station enrolls against
 * (additive; older stations ignore it). `expires_at` is intentionally omitted:
 * perchpub enforces the TTL, and the station ignores it. No chain, keypair, or CSR.
 */
export function buildEnrollQrPayload(session: {
	session_id: string;
	auth_token: string;
	ca_pin: string;
	perchpub_url: string;
}): string {
	return JSON.stringify({
		session_id: session.session_id,
		auth_token: session.auth_token,
		ca_pin: session.ca_pin,
		perchpub_url: session.perchpub_url
	});
}

/** Error-correction level for the enrollment QR — high enough for the screen→camera path. */
export const ENROLL_QR_EC_LEVEL = 'M' as const;

/**
 * The qrcode input for the enrollment symbol: a single explicit **byte-mode**
 * segment carrying the compact JSON payload as raw UTF-8 bytes. Passing an
 * explicit byte segment (rather than a bare string) stops qrcode's auto-optimizer
 * from splitting the payload into mixed numeric/alphanumeric segments — the
 * perchstation contract mandates one byte-mode symbol. The wizard and the
 * conformance test both encode through this helper so they cannot drift.
 */
export function enrollQrSegments(session: {
	session_id: string;
	auth_token: string;
	ca_pin: string;
	perchpub_url: string;
}): { data: Uint8Array; mode: 'byte' }[] {
	return [{ data: new TextEncoder().encode(buildEnrollQrPayload(session)), mode: 'byte' }];
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
	values?: { latitude: string; longitude: string; is_private: boolean };
	formError?: string;
}

/**
 * Default enrollment-session TTL in seconds — mirrors the backend
 * `settings.ENROLLMENT_TTL_SECONDS` default. The live countdown derives purely
 * from `expires_at`, so this is a reference/default, not a hardcoded window.
 */
export const ENROLLMENT_TTL_SECONDS = 60;

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
