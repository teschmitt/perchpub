<script lang="ts">
	import { enhance } from '$app/forms';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const editUser = $derived(data.editUser);
	const email = $derived(form?.values?.email ?? editUser.email);
	const fullName = $derived(form?.values?.full_name ?? editUser.full_name ?? '');
	const isActive = $derived(form?.values?.is_active ?? editUser.is_active);
	const isSuperuser = $derived(form?.values?.is_superuser ?? editUser.is_superuser);
</script>

<svelte:head>
	<title>Edit user · PerchPub</title>
</svelte:head>

<section class="mx-auto max-w-lg space-y-6">
	<div>
		<a href="/admin/users" class="text-sm text-muted-foreground hover:text-primary">← Users</a>
		<h1 class="mt-2 text-2xl font-semibold text-foreground">Edit user</h1>
		<p class="text-sm text-muted-foreground">{editUser.id}</p>
	</div>

	<form
		method="POST"
		action="?/update"
		use:enhance
		data-testid="edit-user-form"
		class="flex flex-col gap-4"
	>
		{#if form?.formError}
			<p
				data-testid="form-error"
				role="alert"
				class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
			>
				{form.formError}
			</p>
		{/if}

		<label class="flex flex-col gap-1 text-sm font-medium" for="email">
			Email
			<input
				id="email"
				name="email"
				type="email"
				required
				data-testid="edit-email"
				value={email}
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
			{#if form?.fieldErrors?.email}
				<span data-testid="edit-email-error" class="text-xs text-destructive">
					{form.fieldErrors.email}
				</span>
			{/if}
		</label>

		<label class="flex flex-col gap-1 text-sm font-medium" for="full_name">
			Full name
			<input
				id="full_name"
				name="full_name"
				type="text"
				data-testid="edit-full-name"
				value={fullName}
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
		</label>

		<label class="flex flex-col gap-1 text-sm font-medium" for="password">
			New password <span class="font-normal text-muted-foreground">(leave blank to keep)</span>
			<input
				id="password"
				name="password"
				type="password"
				autocomplete="new-password"
				minlength="8"
				data-testid="edit-password"
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
		</label>

		<label class="flex items-center gap-2 text-sm font-medium">
			<input
				name="is_active"
				type="checkbox"
				data-testid="edit-is-active"
				checked={isActive}
				class="size-4 rounded border-input"
			/>
			Active
		</label>
		<label class="flex items-center gap-2 text-sm font-medium">
			<input
				name="is_superuser"
				type="checkbox"
				data-testid="edit-is-superuser"
				checked={isSuperuser}
				class="size-4 rounded border-input"
			/>
			Superuser
		</label>

		<button
			type="submit"
			data-testid="edit-submit"
			class="mt-2 self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			Save user
		</button>
	</form>
</section>
