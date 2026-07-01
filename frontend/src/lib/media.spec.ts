import { describe, expect, it } from 'vitest';
import { absoluteMediaUrl, isVideoObject, mediaUrl } from './media';

describe('mediaUrl', () => {
	it('maps an object_name to a same-origin /media URL', () => {
		expect(mediaUrl('ab/cd/abcd1234.jpg')).toBe('/media/ab/cd/abcd1234.jpg');
	});

	it('normalises a leading slash so the result is not /media//...', () => {
		expect(mediaUrl('/ab/cd/x.mp4')).toBe('/media/ab/cd/x.mp4');
	});
});

describe('isVideoObject', () => {
	it('detects video keys by extension', () => {
		expect(isVideoObject('ab/cd/clip.mp4')).toBe(true);
		expect(isVideoObject('ab/cd/clip.WEBM')).toBe(true);
		expect(isVideoObject('ab/cd/clip.mov')).toBe(true);
	});

	it('treats image and extensionless keys as non-video', () => {
		expect(isVideoObject('ab/cd/photo.jpg')).toBe(false);
		expect(isVideoObject('ab/cd/photo.png')).toBe(false);
		expect(isVideoObject('ab/cd/noextension')).toBe(false);
	});
});

describe('absoluteMediaUrl', () => {
	it('joins a public base with the /media path', () => {
		expect(absoluteMediaUrl('ab/cd/x.jpg', 'https://perchpub.example')).toBe(
			'https://perchpub.example/media/ab/cd/x.jpg'
		);
	});

	it('does not double the slash when the base has a trailing slash', () => {
		expect(absoluteMediaUrl('x.jpg', 'https://perchpub.example/')).toBe(
			'https://perchpub.example/media/x.jpg'
		);
	});
});
