import { describe, expect, it } from 'vitest';
import {
	classifyBadgeClass,
	classifyStatusBadge,
	isClassifyStatus,
	latestClassifyStatus,
	type ClassifyBadgeVariant
} from './classify';
import type { components } from '$lib/api/schema';

type ClassifyTaskStatus = components['schemas']['ClassifyTaskStatus'];

const ALL_STATUSES: ClassifyTaskStatus[] = [
	'Prepared',
	'Queued',
	'Processing',
	'Success',
	'Failed'
];

describe('classifyStatusBadge', () => {
	it('labels each ClassifyTaskStatus with its own name', () => {
		for (const status of ALL_STATUSES) {
			expect(classifyStatusBadge(status).label).toBe(status);
		}
	});

	it('gives Failed a variant distinct from every non-failed status', () => {
		const failed = classifyStatusBadge('Failed').variant;
		for (const status of ALL_STATUSES.filter((s) => s !== 'Failed')) {
			expect(classifyStatusBadge(status).variant).not.toBe(failed);
		}
	});
});

describe('classifyBadgeClass', () => {
	const VARIANTS: ClassifyBadgeVariant[] = ['pending', 'progress', 'success', 'failed'];

	it('returns a non-empty class for every variant', () => {
		for (const variant of VARIANTS) {
			expect(classifyBadgeClass(variant)).toBeTruthy();
		}
	});

	it('styles the failed variant distinctly from every non-failed variant', () => {
		const failed = classifyBadgeClass('failed');
		for (const variant of VARIANTS.filter((v) => v !== 'failed')) {
			expect(classifyBadgeClass(variant)).not.toBe(failed);
		}
	});
});

describe('isClassifyStatus', () => {
	it('accepts every valid ClassifyTaskStatus', () => {
		for (const status of ALL_STATUSES) {
			expect(isClassifyStatus(status)).toBe(true);
		}
	});

	it('rejects unknown, empty, and nullish values', () => {
		expect(isClassifyStatus('bogus')).toBe(false);
		expect(isClassifyStatus('')).toBe(false);
		expect(isClassifyStatus(null)).toBe(false);
		expect(isClassifyStatus(undefined)).toBe(false);
	});
});

describe('latestClassifyStatus', () => {
	it('returns null when the observation has no classify task', () => {
		expect(latestClassifyStatus([])).toBeNull();
	});

	it('returns the first task status (list is ordered created_at DESC = most recent first)', () => {
		expect(latestClassifyStatus([{ status: 'Success' }, { status: 'Failed' }])).toBe('Success');
	});
});
