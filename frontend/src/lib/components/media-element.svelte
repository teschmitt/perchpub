<script lang="ts">
	import { isVideoObject, mediaUrl } from '$lib/media';

	let {
		objectName,
		alt,
		controls = false,
		class: className = ''
	}: { objectName: string; alt: string; controls?: boolean; class?: string } = $props();

	const src = $derived(mediaUrl(objectName));
	const isVideo = $derived(isVideoObject(objectName));
</script>

{#if isVideo}
	<video
		{src}
		{controls}
		aria-label={alt}
		muted={!controls}
		playsinline
		preload="metadata"
		class={className}
		data-testid="media-video"
	></video>
{:else}
	<img {src} {alt} loading="lazy" class={className} data-testid="media-image" />
{/if}
