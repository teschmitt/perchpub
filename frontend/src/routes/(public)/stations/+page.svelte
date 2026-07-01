<script lang="ts">
	import Pagination from '$lib/components/pagination.svelte';
	import { stationLabel } from '$lib/format';
	import { paginate, shouldShowPagination } from '$lib/pagination';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const state = $derived(paginate(data.page, data.limit, data.count));
</script>

<svelte:head>
	<title>Stations — PerchPub</title>
	<meta name="description" content="Bird-feeder stations publishing observations to PerchPub." />
</svelte:head>

<section class="space-y-6">
	<h1 class="text-3xl font-bold tracking-tight text-foreground">Stations</h1>

	{#if data.items.length === 0}
		<p
			data-testid="stations-empty"
			class="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground"
		>
			{data.count === 0 ? 'No stations to show.' : 'No stations on this page.'}
		</p>
	{:else}
		<ul data-testid="stations-list" class="grid gap-4 sm:grid-cols-2">
			{#each data.items as station (station.id)}
				<li>
					<a
						href={`/stations/${station.id}`}
						data-testid="station-item"
						class="block rounded-lg border border-border bg-card p-4 transition hover:shadow-md"
					>
						<div class="flex items-center justify-between gap-2">
							<span class="font-medium text-foreground">{stationLabel(station)}</span>
							{#if station.is_private}
								<span
									data-testid="private-badge"
									class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
								>
									Private
								</span>
							{/if}
						</div>
						<p class="mt-1 text-sm text-muted-foreground">
							{station.latitude.toFixed(4)}, {station.longitude.toFixed(4)}
						</p>
					</a>
				</li>
			{/each}
		</ul>
	{/if}

	{#if shouldShowPagination(data.page, data.limit, data.count)}
		<Pagination {state} />
	{/if}
</section>
