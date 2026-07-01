<script lang="ts">
	import { enhance } from '$app/forms';
	import type { ActionData } from './$types';

	let { form }: { form: ActionData } = $props();

	const values = $derived(form?.values ?? { latitude: '', longitude: '', is_private: false });
</script>

<svelte:head>
	<title>New station · PerchPub</title>
</svelte:head>

<section class="mx-auto max-w-lg space-y-6">
	<div>
		<a href="/stations/mine" class="text-sm text-muted-foreground hover:text-primary"
			>← My stations</a
		>
		<h1 class="mt-2 text-2xl font-semibold text-foreground">New station</h1>
	</div>

	<form method="POST" use:enhance data-testid="station-form" class="flex flex-col gap-4">
		{#if form?.formError}
			<p
				data-testid="form-error"
				role="alert"
				class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
			>
				{form.formError}
			</p>
		{/if}

		<label class="flex flex-col gap-1 text-sm font-medium" for="latitude">
			Latitude
			<!-- Map picker deferred: plain numeric coordinate input for now. -->
			<input
				id="latitude"
				name="latitude"
				type="number"
				step="any"
				min="-90"
				max="90"
				required
				data-testid="latitude-input"
				value={values.latitude}
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
			{#if form?.errors?.latitude}
				<span data-testid="latitude-error" class="text-xs text-destructive">
					{form.errors.latitude}
				</span>
			{/if}
		</label>

		<label class="flex flex-col gap-1 text-sm font-medium" for="longitude">
			Longitude
			<input
				id="longitude"
				name="longitude"
				type="number"
				step="any"
				min="-180"
				max="180"
				required
				data-testid="longitude-input"
				value={values.longitude}
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
			{#if form?.errors?.longitude}
				<span data-testid="longitude-error" class="text-xs text-destructive">
					{form.errors.longitude}
				</span>
			{/if}
		</label>

		<label class="flex items-center gap-2 text-sm font-medium">
			<input
				name="is_private"
				type="checkbox"
				data-testid="is-private-input"
				checked={values.is_private}
				class="size-4 rounded border-input"
			/>
			Private (hidden from other viewers)
		</label>

		<button
			type="submit"
			data-testid="submit"
			class="mt-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			Create station
		</button>
	</form>
</section>
