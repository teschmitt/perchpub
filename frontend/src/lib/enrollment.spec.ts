import { describe, expect, it } from 'vitest';
import {
	ENROLLMENT_TTL_SECONDS,
	findNewStationId,
	formatCountdown,
	isExpired,
	secondsRemaining
} from './enrollment';

const EXPIRES = '2026-07-01T12:10:00.000Z';
const CREATED = Date.parse('2026-07-01T12:00:00.000Z'); // 600s (10 min) before expiry

describe('secondsRemaining', () => {
	it('reports the full TTL at the moment of creation', () => {
		expect(secondsRemaining(EXPIRES, CREATED)).toBe(ENROLLMENT_TTL_SECONDS);
	});

	it('counts down as time passes', () => {
		expect(secondsRemaining(EXPIRES, CREATED + 30_000)).toBe(570);
	});

	it('clamps to zero at and past the deadline', () => {
		expect(secondsRemaining(EXPIRES, Date.parse(EXPIRES))).toBe(0);
		expect(secondsRemaining(EXPIRES, Date.parse(EXPIRES) + 5_000)).toBe(0);
	});

	it('returns zero for an unparseable timestamp rather than NaN', () => {
		expect(secondsRemaining('not-a-date', CREATED)).toBe(0);
	});
});

describe('isExpired', () => {
	it('is false before the deadline and true at/after it', () => {
		expect(isExpired(EXPIRES, CREATED)).toBe(false);
		expect(isExpired(EXPIRES, Date.parse(EXPIRES))).toBe(true);
		expect(isExpired(EXPIRES, Date.parse(EXPIRES) + 1)).toBe(true);
	});
});

describe('formatCountdown', () => {
	it('formats seconds as m:ss', () => {
		expect(formatCountdown(300)).toBe('5:00');
		expect(formatCountdown(65)).toBe('1:05');
		expect(formatCountdown(9)).toBe('0:09');
		expect(formatCountdown(0)).toBe('0:00');
	});

	it('never renders negative time', () => {
		expect(formatCountdown(-10)).toBe('0:00');
	});
});

describe('findNewStationId', () => {
	const user = 'owner-1';
	const existing = { id: 's-old', owner: { id: user, full_name: null } };
	const fresh = { id: 's-new', owner: { id: user, full_name: null } };
	const foreign = { id: 's-foreign', owner: { id: 'other', full_name: null } };

	it('returns the id of an owned station absent from the baseline', () => {
		expect(findNewStationId(['s-old'], [existing, fresh], user)).toBe('s-new');
	});

	it('returns null when no new owned station has appeared', () => {
		expect(findNewStationId(['s-old'], [existing], user)).toBeNull();
	});

	it('ignores newly-visible stations owned by someone else', () => {
		expect(findNewStationId(['s-old'], [existing, foreign], user)).toBeNull();
	});
});
