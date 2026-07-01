<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<svelte:head>
	<title>{data.species.scientific_name} — PerchPub</title>
	<meta
		name="description"
		content={`The species ${data.species.scientific_name} in the PerchPub catalog.`}
	/>
</svelte:head>

<article class="space-y-6">
	<nav class="text-sm text-muted-foreground">
		<a href="/species" class="hover:text-primary">← Species catalog</a>
	</nav>

	<header class="space-y-1">
		<p class="text-sm text-muted-foreground">Species</p>
		<h1 data-testid="species-name" class="text-3xl font-bold italic tracking-tight text-foreground">
			{data.species.scientific_name}
		</h1>
	</header>
</article>
