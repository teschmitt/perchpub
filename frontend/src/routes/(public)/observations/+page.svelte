<script lang="ts">
	import ObservationCard from '$lib/components/observation-card.svelte';
	import Pagination from '$lib/components/pagination.svelte';
	import { paginate, shouldShowPagination } from '$lib/pagination';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const state = $derived(paginate(data.page, data.limit, data.count));
</script>

<svelte:head>
	<title>Observations — PerchPub</title>
	<meta
		name="description"
		content="Recent bird-feeder observations captured by PerchPub stations."
	/>
</svelte:head>

<section class="space-y-6">
	<h1 class="text-3xl font-bold tracking-tight text-foreground">Observations</h1>

	{#if data.items.length === 0}
		<p
			data-testid="observations-empty"
			class="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground"
		>
			No observations on this page.
		</p>
	{:else}
		<div
			data-testid="observation-grid"
			class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4"
		>
			{#each data.items as observation (observation.id)}
				<ObservationCard {observation} />
			{/each}
		</div>
	{/if}

	{#if shouldShowPagination(data.page, data.limit, data.count)}
		<Pagination {state} />
	{/if}
</section>
