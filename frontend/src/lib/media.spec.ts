import { describe, expect, it } from 'vitest';
import { mediaUrl } from './media';

describe('mediaUrl', () => {
	it('maps an object_name to a same-origin /media URL', () => {
		expect(mediaUrl('ab/cd/abcd1234.jpg')).toBe('/media/ab/cd/abcd1234.jpg');
	});

	it('normalises a leading slash so the result is not /media//...', () => {
		expect(mediaUrl('/ab/cd/x.mp4')).toBe('/media/ab/cd/x.mp4');
	});
});
