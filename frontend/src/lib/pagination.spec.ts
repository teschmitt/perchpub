import { describe, expect, it } from 'vitest';
import { DEFAULT_LIMIT, paginate, parsePage, shouldShowPagination, skipFor } from './pagination';

describe('shouldShowPagination', () => {
	it('shows controls when the count exceeds one page', () => {
		expect(shouldShowPagination(1, 24, 25)).toBe(true);
	});

	it('hides controls for a single page on the first page', () => {
		expect(shouldShowPagination(1, 24, 10)).toBe(false);
		expect(shouldShowPagination(1, 24, 0)).toBe(false);
	});

	it('shows controls on any page beyond the first so an out-of-range page keeps Prev', () => {
		expect(shouldShowPagination(2, 24, 10)).toBe(true);
	});
});

describe('parsePage', () => {
	it('defaults a missing page param to 1', () => {
		expect(parsePage(new URLSearchParams())).toBe(1);
	});

	it('reads a valid 1-based page', () => {
		expect(parsePage(new URLSearchParams('page=3'))).toBe(3);
	});

	it('clamps junk, zero, and negatives to 1', () => {
		expect(parsePage(new URLSearchParams('page=abc'))).toBe(1);
		expect(parsePage(new URLSearchParams('page=0'))).toBe(1);
		expect(parsePage(new URLSearchParams('page=-4'))).toBe(1);
		expect(parsePage(new URLSearchParams('page=2.5'))).toBe(1);
	});
});

describe('skipFor', () => {
	it('maps a 1-based page to a zero-based offset', () => {
		expect(skipFor(1, DEFAULT_LIMIT)).toBe(0);
		expect(skipFor(2, 24)).toBe(24);
		expect(skipFor(3, 10)).toBe(20);
	});

	it('never returns a negative offset', () => {
		expect(skipFor(0, 24)).toBe(0);
	});
});

describe('paginate', () => {
	it('disables prev on the first page', () => {
		const state = paginate(1, 24, 100);
		expect(state.hasPrev).toBe(false);
		expect(state.hasNext).toBe(true);
		expect(state.nextPage).toBe(2);
	});

	it('disables next once skip + limit >= count', () => {
		// page 1 of exactly one full page: 1*24 == 24, not < 24 → no next.
		expect(paginate(1, 24, 24).hasNext).toBe(false);
		// page 2 of 25 items: skip 24, 24+24=48 >= 25 → no next, prev enabled.
		const last = paginate(2, 24, 25);
		expect(last.hasNext).toBe(false);
		expect(last.hasPrev).toBe(true);
		expect(last.prevPage).toBe(1);
	});

	it('keeps next disabled and prev enabled on an out-of-range page', () => {
		// skip (3-1)*24 = 48 >= count 10 → empty slice, but not an error.
		const beyond = paginate(3, 24, 10);
		expect(beyond.hasNext).toBe(false);
		expect(beyond.hasPrev).toBe(true);
	});
});
