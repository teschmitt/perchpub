import { describe, expect, it } from 'vitest';
import { isOwnStation, parseStationForm } from './stations';

function formOf(entries: Record<string, string>): FormData {
	const fd = new FormData();
	for (const [k, v] of Object.entries(entries)) {
		fd.append(k, v);
	}
	return fd;
}

describe('parseStationForm', () => {
	it('parses valid coordinates and an unchecked privacy flag', () => {
		const result = parseStationForm(formOf({ latitude: '52.5', longitude: '13.4' }));
		expect(result).toEqual({
			ok: true,
			value: { latitude: 52.5, longitude: 13.4, is_private: false }
		});
	});

	it('treats a present is_private checkbox as true', () => {
		const result = parseStationForm(formOf({ latitude: '0', longitude: '0', is_private: 'on' }));
		expect(result.ok && result.value.is_private).toBe(true);
	});

	it('rejects a latitude outside -90..90 with a field error and keeps the raw values', () => {
		const result = parseStationForm(formOf({ latitude: '91', longitude: '13.4' }));
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.errors.latitude).toMatch(/-90/);
			expect(result.errors.longitude).toBeUndefined();
			expect(result.values).toEqual({ latitude: '91', longitude: '13.4', is_private: false });
		}
	});

	it('rejects a longitude outside -180..180', () => {
		const result = parseStationForm(formOf({ latitude: '0', longitude: '200' }));
		expect(result.ok).toBe(false);
		if (!result.ok) {
			expect(result.errors.longitude).toMatch(/-180/);
		}
	});

	it('rejects non-numeric and empty coordinates', () => {
		const nan = parseStationForm(formOf({ latitude: 'abc', longitude: '10' }));
		expect(nan.ok).toBe(false);
		const empty = parseStationForm(formOf({ latitude: '', longitude: '' }));
		expect(empty.ok).toBe(false);
		if (!empty.ok) {
			expect(empty.errors.latitude).toBeDefined();
			expect(empty.errors.longitude).toBeDefined();
		}
	});
});

describe('isOwnStation', () => {
	const mine = { owner: { id: 'u1', full_name: null } };
	const theirs = { owner: { id: 'u2', full_name: null } };
	const ownerless = { owner: null };

	it('matches a station owned by the given user', () => {
		expect(isOwnStation(mine, 'u1')).toBe(true);
	});

	it('rejects a foreign or ownerless station', () => {
		expect(isOwnStation(theirs, 'u1')).toBe(false);
		expect(isOwnStation(ownerless, 'u1')).toBe(false);
	});
});
