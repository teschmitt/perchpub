/**
 * Pagination math over the backend's `{data, count}` list envelope. Kept as pure
 * functions (no SvelteKit imports) so server `load` code and the pagination
 * component share one source of truth and the skip/limit logic is unit-testable.
 */

/** Default page size for the public list pages. */
export const DEFAULT_LIMIT = 24;

/** Parse a 1-based `?page` query param, clamping junk / zero / negatives to 1. */
export function parsePage(searchParams: URLSearchParams): number {
	const raw = Number(searchParams.get('page'));
	if (!Number.isInteger(raw) || raw < 1) {
		return 1;
	}
	return raw;
}

/** Zero-based offset for a 1-based page (never negative). */
export function skipFor(page: number, limit: number): number {
	return Math.max(0, (page - 1) * limit);
}

export interface PaginationState {
	page: number;
	limit: number;
	count: number;
	hasPrev: boolean;
	hasNext: boolean;
	prevPage: number;
	nextPage: number;
}

/**
 * Derive prev/next availability from the response `count`: prev is enabled past
 * the first page, next while `skip + limit < count`. An out-of-range page (skip
 * >= count) therefore yields an empty slice with next disabled — not an error.
 */
export function paginate(page: number, limit: number, count: number): PaginationState {
	return {
		page,
		limit,
		count,
		hasPrev: page > 1,
		hasNext: page * limit < count,
		prevPage: page - 1,
		nextPage: page + 1
	};
}

/**
 * Whether to render pagination controls: when the count spills past one page, or
 * on any page beyond the first — so a manually-requested out-of-range page still
 * exposes a Previous link rather than becoming a navigational dead-end.
 */
export function shouldShowPagination(page: number, limit: number, count: number): boolean {
	return count > limit || page > 1;
}
