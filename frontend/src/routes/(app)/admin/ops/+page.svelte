<script lang="ts">
	import { enhance } from '$app/forms';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();
</script>

<svelte:head>
	<title>Ops · PerchPub</title>
</svelte:head>

<section class="mx-auto max-w-lg space-y-8">
	<h1 class="text-2xl font-semibold text-foreground">Ops</h1>

	<!-- Health -->
	<div class="space-y-2 rounded-lg border border-border p-5">
		<h2 class="text-lg font-medium text-foreground">Backend health</h2>
		{#if data.healthy}
			<p data-testid="health-status" class="flex items-center gap-2 text-sm text-primary">
				<span class="inline-block size-2 rounded-full bg-primary"></span>
				Healthy
			</p>
		{:else}
			<p data-testid="health-status" class="flex items-center gap-2 text-sm text-destructive">
				<span class="inline-block size-2 rounded-full bg-destructive"></span>
				Unreachable
			</p>
		{/if}
	</div>

	<!-- Test email -->
	<div class="space-y-4 rounded-lg border border-border p-5">
		<h2 class="text-lg font-medium text-foreground">Send test email</h2>
		<p class="text-sm text-muted-foreground">
			Sends via the backend's configured mail settings. Fails if email is not configured.
		</p>

		{#if form?.message}
			<p
				data-testid="email-success"
				role="status"
				class="rounded-md bg-primary/10 px-3 py-2 text-sm text-primary"
			>
				{form.message}
			</p>
		{/if}
		{#if form?.error}
			<p
				data-testid="email-error"
				role="alert"
				class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
			>
				{form.error}
			</p>
		{/if}

		<form
			method="POST"
			action="?/test-email"
			use:enhance
			data-testid="test-email-form"
			class="flex flex-wrap items-end gap-3"
		>
			<label class="flex flex-col gap-1 text-sm font-medium" for="email_to">
				Send to
				<input
					id="email_to"
					name="email_to"
					type="email"
					required
					data-testid="test-email-input"
					class="min-w-64 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
			</label>
			<button
				type="submit"
				data-testid="test-email-submit"
				class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				Send test email
			</button>
		</form>
	</div>
</section>
