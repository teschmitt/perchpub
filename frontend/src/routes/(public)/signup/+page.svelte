<script lang="ts">
	import { enhance } from '$app/forms';
	import type { ActionData } from './$types';

	let { form }: { form: ActionData } = $props();
</script>

<svelte:head>
	<title>Sign up · PerchPub</title>
</svelte:head>

<section class="mx-auto max-w-sm space-y-6">
	<h1 class="text-2xl font-semibold text-foreground">Create your PerchPub account</h1>

	<!-- A successful signup signs the account in and redirects into first-station
	     setup, so the page only needs to re-render validation/upstream errors. -->
	<form method="POST" use:enhance data-testid="signup-form" class="flex flex-col gap-4">
		{#if form?.error}
			<p
				data-testid="signup-error"
				role="alert"
				class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
			>
				{form.error}
			</p>
		{/if}

		<label class="flex flex-col gap-1 text-sm font-medium" for="full_name">
			Full name (optional)
			<input
				id="full_name"
				name="full_name"
				type="text"
				autocomplete="name"
				data-testid="full-name-input"
				value={form?.values?.full_name ?? ''}
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
		</label>

		<label class="flex flex-col gap-1 text-sm font-medium" for="email">
			Email
			<input
				id="email"
				name="email"
				type="email"
				autocomplete="username"
				required
				data-testid="email-input"
				value={form?.values?.email ?? ''}
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
		</label>

		<label class="flex flex-col gap-1 text-sm font-medium" for="password">
			Password
			<input
				id="password"
				name="password"
				type="password"
				autocomplete="new-password"
				required
				minlength="8"
				data-testid="password-input"
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
		</label>

		<button
			type="submit"
			data-testid="submit"
			class="mt-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			Sign up
		</button>
	</form>

	<p class="text-center text-sm text-muted-foreground">
		Already have an account?
		<a href="/login" class="text-primary hover:underline">Log in</a>
	</p>
</section>
