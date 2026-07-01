<script lang="ts">
	import type { components } from '$lib/api/schema';
	import { formatConfidence, formatDate, stationLabel } from '$lib/format';
	import MediaElement from './media-element.svelte';

	type ObservationPublic = components['schemas']['ObservationPublic'];

	let { observation }: { observation: ObservationPublic } = $props();

	const speciesName = $derived(observation.species?.scientific_name ?? 'Unclassified');
	const confidence = $derived(formatConfidence(observation.confidence_score));
	const station = $derived(stationLabel(observation.station));
</script>

<a
	href={`/observations/${observation.id}`}
	data-testid="observation-card"
	class="group block overflow-hidden rounded-lg border border-border bg-card transition hover:shadow-md"
>
	<div class="aspect-square w-full overflow-hidden bg-muted">
		<MediaElement
			objectName={observation.object_name}
			alt={speciesName}
			class="h-full w-full object-cover transition group-hover:scale-105"
		/>
	</div>
	<div class="space-y-1 p-3">
		<p class="font-medium text-foreground" class:italic={observation.species !== null}>
			{speciesName}
		</p>
		<p class="truncate text-sm text-muted-foreground">{station}</p>
		<div class="flex items-center justify-between text-xs text-muted-foreground">
			<time datetime={observation.observed_at}>{formatDate(observation.observed_at)}</time>
			{#if confidence}
				<span data-testid="confidence">{confidence}</span>
			{/if}
		</div>
	</div>
</a>
