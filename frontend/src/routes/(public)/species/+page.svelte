<script lang="ts">
	import Pagination from '$lib/components/pagination.svelte';
	import { paginate, shouldShowPagination } from '$lib/pagination';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const state = $derived(paginate(data.page, data.limit, data.count));
</script>

<svelte:head>
	<title>Species — PerchPub</title>
	<meta name="description" content="The catalog of bird species observed at PerchPub feeders." />
</svelte:head>

<section class="space-y-6">
	<h1 class="text-3xl font-bold tracking-tight text-foreground">Species</h1>

	{#if data.items.length === 0}
		<p
			data-testid="species-empty"
			class="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground"
		>
			{data.count === 0 ? 'No species recorded yet.' : 'No species on this page.'}
		</p>
	{:else}
		<ul data-testid="species-list" class="divide-y divide-border rounded-lg border border-border">
			{#each data.items as species (species.id)}
				<li>
					<a href={`/species/${species.id}`} class="block px-4 py-3 italic hover:bg-accent">
						{species.scientific_name}
					</a>
				</li>
			{/each}
		</ul>
	{/if}

	{#if shouldShowPagination(data.page, data.limit, data.count)}
		<Pagination {state} />
	{/if}
</section>
