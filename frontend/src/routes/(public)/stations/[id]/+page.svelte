<script lang="ts">
	import { stationLabel } from '$lib/format';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const station = $derived(data.station);
</script>

<svelte:head>
	<title>{stationLabel(station)} — PerchPub</title>
	<meta name="description" content="A bird-feeder station on PerchPub." />
</svelte:head>

<article class="space-y-6">
	<nav class="text-sm text-muted-foreground">
		<a href="/stations" class="hover:text-primary">← All stations</a>
	</nav>

	<header class="flex items-center justify-between gap-2">
		<h1 data-testid="station-name" class="text-3xl font-bold tracking-tight text-foreground">
			{stationLabel(station)}
		</h1>
		{#if station.is_private}
			<span
				data-testid="private-badge"
				class="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground"
			>
				Private
			</span>
		{/if}
	</header>

	<dl class="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
		<div class="flex justify-between gap-4 border-b border-border py-1">
			<dt class="text-muted-foreground">Location</dt>
			<dd class="font-medium">{station.latitude.toFixed(4)}, {station.longitude.toFixed(4)}</dd>
		</div>
		<div class="flex justify-between gap-4 border-b border-border py-1">
			<dt class="text-muted-foreground">Owner</dt>
			<dd class="font-medium">{station.owner?.full_name ?? 'Unattributed'}</dd>
		</div>
		<div class="flex justify-between gap-4 border-b border-border py-1">
			<dt class="text-muted-foreground">Visibility</dt>
			<dd class="font-medium">{station.is_private ? 'Private' : 'Public'}</dd>
		</div>
	</dl>
</article>
