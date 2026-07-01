<script lang="ts">
	import MediaElement from '$lib/components/media-element.svelte';
	import { formatConfidence, formatDate, stationLabel } from '$lib/format';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const observation = $derived(data.observation);
	const speciesName = $derived(observation.species?.scientific_name ?? 'Unclassified');
	const confidence = $derived(formatConfidence(observation.confidence_score));
	const station = $derived(stationLabel(observation.station));
</script>

<svelte:head>
	<title>{data.meta.title} — PerchPub</title>
	<meta name="description" content={data.meta.description} />
	<meta property="og:type" content="website" />
	<meta property="og:title" content={data.meta.title} />
	<meta property="og:description" content={data.meta.description} />
	<meta property="og:url" content={data.meta.url} />
	<meta property="og:image" content={data.meta.image} />
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content={data.meta.title} />
	<meta name="twitter:description" content={data.meta.description} />
	<meta name="twitter:image" content={data.meta.image} />
</svelte:head>

<article class="space-y-6">
	<nav class="text-sm text-muted-foreground">
		<a href="/observations" class="hover:text-primary">← All observations</a>
	</nav>

	<div class="overflow-hidden rounded-lg border border-border bg-muted">
		<MediaElement
			objectName={observation.object_name}
			alt={speciesName}
			controls
			class="max-h-[70vh] w-full object-contain"
		/>
	</div>

	<header class="space-y-2">
		<h1
			class="text-3xl font-bold tracking-tight text-foreground"
			class:italic={observation.species !== null}
		>
			{#if observation.species}
				<a
					href={`/species/${observation.species.id}`}
					data-testid="species-link"
					class="hover:underline"
				>
					{speciesName}
				</a>
			{:else}
				{speciesName}
			{/if}
		</h1>
		<dl class="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
			<div class="flex justify-between gap-4 border-b border-border py-1">
				<dt class="text-muted-foreground">Station</dt>
				<dd>
					<a
						href={`/stations/${observation.station.id}`}
						data-testid="station-link"
						class="font-medium text-primary hover:underline"
					>
						{station}
					</a>
				</dd>
			</div>
			<div class="flex justify-between gap-4 border-b border-border py-1">
				<dt class="text-muted-foreground">Observed</dt>
				<dd>
					<time datetime={observation.observed_at} class="font-medium">
						{formatDate(observation.observed_at)}
					</time>
				</dd>
			</div>
			<div class="flex justify-between gap-4 border-b border-border py-1">
				<dt class="text-muted-foreground">Confidence</dt>
				<dd class="font-medium" data-testid="confidence">{confidence ?? '—'}</dd>
			</div>
		</dl>
	</header>
</article>
