<script lang="ts">
	import { enhance } from '$app/forms';
	import type { ActionData } from './$types';

	let { form }: { form: ActionData } = $props();
</script>

<svelte:head>
	<title>Log in · PerchPub</title>
</svelte:head>

<main class="flex min-h-screen items-center justify-center bg-background px-4">
	<div class="w-full max-w-sm rounded-lg border border-border bg-card p-8 shadow-sm">
		<h1 class="mb-6 text-2xl font-semibold text-card-foreground">Log in to PerchPub</h1>

		<form method="POST" use:enhance class="flex flex-col gap-4">
			{#if form?.error}
				<p
					data-testid="login-error"
					role="alert"
					class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
				>
					{form.error}
				</p>
			{/if}

			<label class="flex flex-col gap-1 text-sm font-medium" for="email">
				Email
				<input
					id="email"
					name="username"
					type="email"
					autocomplete="username"
					data-testid="email-input"
					value={form?.username ?? ''}
					required
					class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
			</label>

			<label class="flex flex-col gap-1 text-sm font-medium" for="password">
				Password
				<input
					id="password"
					name="password"
					type="password"
					autocomplete="current-password"
					data-testid="password-input"
					required
					class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
			</label>

			<button
				type="submit"
				class="mt-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				Log In
			</button>
		</form>

		<p class="mt-6 text-center text-sm text-muted-foreground">
			New to PerchPub?
			<a href="/signup" data-testid="signup-link" class="text-primary hover:underline">
				Create an account
			</a>
		</p>
	</div>
</main>
