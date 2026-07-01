<script lang="ts">
	import { enhance } from '$app/forms';
	import ClassifyStatusBadge from '$lib/components/classify-status-badge.svelte';
	import MediaElement from '$lib/components/media-element.svelte';
	import { formatConfidence, formatDate, stationLabel } from '$lib/format';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const observation = $derived(data.observation);
	const speciesName = $derived(observation.species?.scientific_name ?? 'Unclassified');
	const confidence = $derived(formatConfidence(observation.confidence_score));
	const station = $derived(stationLabel(observation.station));
	const isSuperuser = $derived(data.user?.is_superuser ?? false);
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
		<div class="flex flex-wrap items-center gap-2">
			{#if data.latestStatus}
				<ClassifyStatusBadge status={data.latestStatus} />
			{/if}
			{#if form?.reclassified}
				<span
					data-testid="manually-classified"
					class="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
				>
					Manually classified
				</span>
			{/if}
		</div>
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

	{#if isSuperuser}
		<!-- Superuser-only manual reclassification. The backend PUT is superuser-guarded. -->
		<section data-testid="reclassify" class="space-y-3 rounded-lg border border-border p-5">
			<h2 class="text-lg font-medium text-foreground">Reclassify</h2>
			{#if form?.reclassifyError}
				<p
					data-testid="reclassify-error"
					role="alert"
					class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
				>
					{form.reclassifyError}
				</p>
			{/if}
			<form method="POST" action="?/reclassify" use:enhance class="flex flex-wrap items-end gap-3">
				<label class="flex flex-col gap-1 text-sm font-medium" for="species_id">
					Species
					<select
						id="species_id"
						name="species_id"
						required
						data-testid="reclassify-species"
						class="min-w-64 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
					>
						<option value="" disabled selected>Choose a species…</option>
						{#each data.species as sp (sp.id)}
							<option value={sp.id}>{sp.scientific_name}</option>
						{/each}
					</select>
				</label>
				<button
					type="submit"
					data-testid="reclassify-submit"
					class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
				>
					Reclassify
				</button>
			</form>
		</section>
	{/if}
</article>
