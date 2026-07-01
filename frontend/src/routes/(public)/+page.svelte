<script lang="ts">
	import ObservationCard from '$lib/components/observation-card.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<svelte:head>
	<title>PerchPub — backyard bird-feeder observations</title>
	<meta
		name="description"
		content="PerchPub is a self-hosted bird-feeder observation server: Raspberry Pi stations capture feeder visits, classify the species, and share the observations."
	/>
</svelte:head>

<section data-testid="landing" class="flex flex-col items-start gap-4 py-10">
	<h1 class="text-4xl font-bold tracking-tight text-foreground">PerchPub</h1>
	<p class="max-w-2xl text-lg text-muted-foreground">
		A self-hosted bird-feeder observation server. Stations at the feeder capture photos and short
		videos, classify the visiting species, and publish the observations here.
	</p>
	<div class="flex gap-3">
		<a
			href="/observations"
			class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			Browse observations
		</a>
		<a
			href="/species"
			class="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent"
		>
			Species catalog
		</a>
	</div>
</section>

<section data-testid="recent-observations" class="py-4">
	<div class="mb-4 flex items-baseline justify-between">
		<h2 class="text-xl font-semibold text-foreground">Recent observations</h2>
		<a href="/observations" class="text-sm text-primary hover:underline">View all →</a>
	</div>

	{#if data.observations.length === 0}
		<p
			data-testid="recent-empty"
			class="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground"
		>
			No observations yet. Once a station captures a feeder visit, it will appear here.
		</p>
	{:else}
		<div class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
			{#each data.observations as observation (observation.id)}
				<ObservationCard {observation} />
			{/each}
		</div>
	{/if}
</section>
