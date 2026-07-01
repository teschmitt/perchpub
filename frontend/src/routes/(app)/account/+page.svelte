<script lang="ts">
	import { enhance } from '$app/forms';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const profile = $derived(form?.intent === 'profile' ? form : null);
	const password = $derived(form?.intent === 'password' ? form : null);
	const del = $derived(form?.intent === 'delete' ? form : null);

	const fullName = $derived(profile?.values?.full_name ?? data.user.full_name ?? '');
	const email = $derived(profile?.values?.email ?? data.user.email);

	let confirmDelete = $state(false);
</script>

<svelte:head>
	<title>Account · PerchPub</title>
</svelte:head>

<section class="mx-auto max-w-lg space-y-10">
	<h1 class="text-2xl font-semibold text-foreground">Account</h1>

	<!-- Profile -->
	<div class="space-y-4">
		<h2 class="text-lg font-medium text-foreground">Profile</h2>
		<form
			method="POST"
			action="?/updateProfile"
			use:enhance
			data-testid="profile-form"
			class="flex flex-col gap-4"
		>
			{#if profile?.success}
				<p
					data-testid="profile-success"
					role="status"
					class="rounded-md bg-primary/10 px-3 py-2 text-sm text-primary"
				>
					Profile updated.
				</p>
			{/if}
			{#if profile?.error}
				<p
					data-testid="profile-error"
					role="alert"
					class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
				>
					{profile.error}
				</p>
			{/if}

			<label class="flex flex-col gap-1 text-sm font-medium" for="full_name">
				Full name
				<input
					id="full_name"
					name="full_name"
					type="text"
					data-testid="full-name-input"
					value={fullName}
					class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
			</label>

			<label class="flex flex-col gap-1 text-sm font-medium" for="email">
				Email
				<input
					id="email"
					name="email"
					type="email"
					required
					data-testid="email-input"
					value={email}
					class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
				{#if profile?.fieldErrors?.email}
					<span data-testid="email-error" class="text-xs text-destructive">
						{profile.fieldErrors.email}
					</span>
				{/if}
			</label>

			<button
				type="submit"
				data-testid="save-profile"
				class="mt-1 self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				Save profile
			</button>
		</form>
	</div>

	<!-- Password -->
	<div class="space-y-4">
		<h2 class="text-lg font-medium text-foreground">Change password</h2>
		<form
			method="POST"
			action="?/changePassword"
			use:enhance
			data-testid="password-form"
			class="flex flex-col gap-4"
		>
			{#if password?.success}
				<p
					data-testid="password-success"
					role="status"
					class="rounded-md bg-primary/10 px-3 py-2 text-sm text-primary"
				>
					Password updated.
				</p>
			{/if}
			{#if password?.error}
				<p
					data-testid="password-error"
					role="alert"
					class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
				>
					{password.error}
				</p>
			{/if}

			<label class="flex flex-col gap-1 text-sm font-medium" for="current_password">
				Current password
				<input
					id="current_password"
					name="current_password"
					type="password"
					autocomplete="current-password"
					required
					minlength="8"
					data-testid="current-password-input"
					class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
				{#if password?.fieldErrors?.current_password}
					<span data-testid="current-password-error" class="text-xs text-destructive">
						{password.fieldErrors.current_password}
					</span>
				{/if}
			</label>

			<label class="flex flex-col gap-1 text-sm font-medium" for="new_password">
				New password
				<input
					id="new_password"
					name="new_password"
					type="password"
					autocomplete="new-password"
					required
					minlength="8"
					data-testid="new-password-input"
					class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
				/>
				{#if password?.fieldErrors?.new_password}
					<span data-testid="new-password-error" class="text-xs text-destructive">
						{password.fieldErrors.new_password}
					</span>
				{/if}
			</label>

			<button
				type="submit"
				data-testid="save-password"
				class="mt-1 self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				Change password
			</button>
		</form>
	</div>

	<!-- Delete -->
	<div class="space-y-4 rounded-lg border border-destructive/30 p-5">
		<h2 class="text-lg font-medium text-destructive">Delete account</h2>
		{#if data.user.is_superuser}
			<p data-testid="delete-disabled" class="text-sm text-muted-foreground">
				Superuser accounts cannot be deleted from here.
			</p>
			<button
				type="button"
				disabled
				data-testid="delete-account"
				class="cursor-not-allowed rounded-md bg-destructive/40 px-4 py-2 text-sm font-medium text-destructive-foreground opacity-60"
			>
				Delete account
			</button>
		{:else}
			<p class="text-sm text-muted-foreground">
				This permanently deletes your account. This cannot be undone.
			</p>
			{#if del?.error}
				<p
					data-testid="delete-error"
					role="alert"
					class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
				>
					{del.error}
				</p>
			{/if}
			<form method="POST" action="?/deleteAccount" use:enhance class="space-y-3">
				<label class="flex items-center gap-2 text-sm">
					<input
						type="checkbox"
						name="confirm"
						data-testid="confirm-delete"
						bind:checked={confirmDelete}
						class="size-4 rounded border-input"
					/>
					I understand this permanently deletes my account.
				</label>
				<button
					type="submit"
					disabled={!confirmDelete}
					data-testid="delete-account"
					class="rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
				>
					Delete account
				</button>
			</form>
		{/if}
	</div>
</section>
