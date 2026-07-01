<script lang="ts">
	import { enhance } from '$app/forms';
	import EnrollToken from '$lib/components/enroll-token.svelte';
	import type { EnrollSession } from '$lib/enrollment';
	import type { ActionData } from './$types';

	let { form }: { form: ActionData } = $props();

	// Capture the one-time session in memory-only state so a later "check" submit
	// keeps the token panel visible. Cleared on navigation/reload — never persisted.
	let session = $state<EnrollSession | null>(null);
	let baseline = $state<string[]>([]);

	$effect(() => {
		if (form?.intent === 'create' && form.session) {
			session = form.session;
			baseline = form.baseline ?? [];
		}
	});

	const createValues = $derived(
		form?.intent === 'create'
			? (form.values ?? { latitude: '', longitude: '' })
			: { latitude: '', longitude: '' }
	);
	const checkResult = $derived(form?.intent === 'check' ? form : null);
</script>

<svelte:head>
	<title>Enroll a device · PerchPub</title>
</svelte:head>

<section class="mx-auto max-w-lg space-y-6">
	<h1 class="text-2xl font-semibold text-foreground">Enroll a device</h1>

	{#if !session}
		<p class="text-sm text-muted-foreground">
			Enter the new station's coordinates to start an enrollment session. You'll get a one-time
			token to run on the Raspberry Pi.
		</p>

		<form
			method="POST"
			action="?/create"
			use:enhance
			data-testid="enroll-form"
			class="flex flex-col gap-4"
		>
			{#if form?.intent === 'create' && form.formError}
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
				<input
					id="latitude"
					name="latitude"
					type="number"
					step="any"
					min="-90"
					max="90"
					required
					data-testid="latitude-input"
					value={createValues.latitude}
					class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
				{#if form?.intent === 'create' && form.errors?.latitude}
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
					value={createValues.longitude}
					class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
				{#if form?.intent === 'create' && form.errors?.longitude}
					<span data-testid="longitude-error" class="text-xs text-destructive">
						{form.errors.longitude}
					</span>
				{/if}
			</label>

			<button
				type="submit"
				data-testid="start-enrollment"
				class="mt-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				Start enrollment
			</button>
		</form>
	{:else}
		<EnrollToken
			token={session.auth_token}
			sessionId={session.session_id}
			expiresAt={session.expires_at}
		/>

		<div class="space-y-3 rounded-lg border border-border p-5">
			<h2 class="text-base font-semibold text-foreground">Waiting for the device</h2>
			<p class="text-sm text-muted-foreground">
				Once the Raspberry Pi finishes enrollment, its station appears in your list. There is no
				live status — check when the device reports success.
			</p>

			{#if checkResult && checkResult.newStationId}
				<p data-testid="check-found" class="text-sm text-foreground">
					Your new station is enrolled.
					<a
						href={`/stations/${checkResult.newStationId}/edit`}
						class="text-primary hover:underline"
					>
						Manage it
					</a>
				</p>
			{:else if checkResult}
				<p data-testid="check-pending" class="text-sm text-muted-foreground">
					No new station yet. Give the device a moment, then check again.
				</p>
			{/if}

			<form method="POST" action="?/check" use:enhance>
				<input type="hidden" name="baseline" value={JSON.stringify(baseline)} />
				<button
					type="submit"
					data-testid="check-station"
					class="rounded-md border border-input px-4 py-2 text-sm font-medium hover:bg-accent"
				>
					Check for the new station
				</button>
			</form>
		</div>
	{/if}
</section>
