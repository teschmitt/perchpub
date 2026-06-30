/**
 * Map an observation's stored S3 `object_name` to its same-origin media URL.
 * The SvelteKit `/media/[...path]` endpoint proxies these to the backend media
 * endpoint, so `<img>`/`<video>` sources are plain same-origin URLs.
 */
export function mediaUrl(objectName: string): string {
	return `/media/${objectName.replace(/^\/+/, '')}`;
}
