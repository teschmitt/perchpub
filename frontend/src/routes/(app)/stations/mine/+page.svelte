<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<svelte:head>
	<title>My stations · PerchPub</title>
</svelte:head>

<section class="space-y-6">
	<div class="flex items-center justify-between gap-4">
		<h1 class="text-2xl font-semibold text-foreground">My stations</h1>
		<a
			href="/stations/new"
			data-testid="new-station"
			class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			New station
		</a>
	</div>

	{#if data.stations.length === 0}
		<p
			data-testid="stations-empty"
			class="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground"
		>
			You don't own any stations yet. Create one, or
			<a href="/enroll" class="text-primary hover:underline">enroll a device</a>.
		</p>
	{:else}
		<ul data-testid="my-stations" class="grid gap-4 sm:grid-cols-2">
			{#each data.stations as station (station.id)}
				<li data-testid="station-item" class="rounded-lg border border-border bg-card p-4">
					<div class="flex items-center justify-between gap-2">
						<span class="font-medium text-foreground">
							{station.latitude.toFixed(4)}, {station.longitude.toFixed(4)}
						</span>
						{#if station.is_private}
							<span
								data-testid="private-badge"
								class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
							>
								Private
							</span>
						{/if}
					</div>
					<a
						href={`/stations/${station.id}/edit`}
						data-testid="edit-station"
						class="mt-3 inline-block text-sm text-primary hover:underline"
					>
						Edit
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</section>
