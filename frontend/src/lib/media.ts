/**
 * Map an observation's stored S3 `object_name` to its same-origin media URL.
 * The SvelteKit `/media/[...path]` endpoint proxies these to the backend media
 * endpoint, so `<img>`/`<video>` sources are plain same-origin URLs.
 */
export function mediaUrl(objectName: string): string {
	return `/media/${objectName.replace(/^\/+/, '')}`;
}

/** Object-key extensions rendered as `<video>` rather than `<img>`. */
const VIDEO_EXTENSIONS = new Set(['mp4', 'webm', 'mov', 'm4v', 'ogv', 'ogg']);

/** True when the object key is a video (by extension), so the UI uses `<video>`. */
export function isVideoObject(objectName: string): boolean {
	const ext = objectName.split('.').pop()?.toLowerCase() ?? '';
	return VIDEO_EXTENSIONS.has(ext);
}

/**
 * Absolute same-origin media URL for Open Graph / share `<meta>` tags, built on a
 * public base (`PUBLIC_SITE_URL`, or the request origin as a dev fallback). The
 * base's trailing slash is normalised so the result is never `.../media//...`.
 */
export function absoluteMediaUrl(objectName: string, base: string): string {
	return `${base.replace(/\/+$/, '')}${mediaUrl(objectName)}`;
}
