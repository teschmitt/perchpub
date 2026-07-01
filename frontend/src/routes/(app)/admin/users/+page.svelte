<script lang="ts">
	import { enhance } from '$app/forms';
	import Pagination from '$lib/components/pagination.svelte';
	import { paginate, shouldShowPagination } from '$lib/pagination';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const create = $derived(form?.intent === 'create' ? form : null);
	const del = $derived(form?.intent === 'delete' ? form : null);
	const values = $derived(
		create?.values ?? { email: '', full_name: '', is_active: true, is_superuser: false }
	);
	const state = $derived(paginate(data.page, data.limit, data.count));
</script>

<svelte:head>
	<title>Users · PerchPub</title>
</svelte:head>

<section class="space-y-8">
	<h1 class="text-2xl font-semibold text-foreground">Users</h1>

	<!-- Create -->
	<form
		method="POST"
		action="?/create"
		use:enhance
		data-testid="create-user-form"
		class="grid gap-4 rounded-lg border border-border p-5 sm:grid-cols-2"
	>
		<h2 class="text-lg font-medium text-foreground sm:col-span-2">Create user</h2>
		{#if create?.formError}
			<p
				data-testid="create-error"
				role="alert"
				class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive sm:col-span-2"
			>
				{create.formError}
			</p>
		{/if}

		<label class="flex flex-col gap-1 text-sm font-medium" for="email">
			Email
			<input
				id="email"
				name="email"
				type="email"
				required
				data-testid="create-email"
				value={values.email}
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
				data-testid="create-password"
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
		</label>

		<label class="flex flex-col gap-1 text-sm font-medium sm:col-span-2" for="full_name">
			Full name
			<input
				id="full_name"
				name="full_name"
				type="text"
				data-testid="create-full-name"
				value={values.full_name}
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
		</label>

		<label class="flex items-center gap-2 text-sm font-medium">
			<input
				name="is_active"
				type="checkbox"
				data-testid="create-is-active"
				checked={values.is_active}
				class="size-4 rounded border-input"
			/>
			Active
		</label>
		<label class="flex items-center gap-2 text-sm font-medium">
			<input
				name="is_superuser"
				type="checkbox"
				data-testid="create-is-superuser"
				checked={values.is_superuser}
				class="size-4 rounded border-input"
			/>
			Superuser
		</label>

		<button
			type="submit"
			data-testid="create-submit"
			class="self-start rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 sm:col-span-2"
		>
			Create user
		</button>
	</form>

	{#if del?.error}
		<p
			data-testid="delete-error"
			role="alert"
			class="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
		>
			{del.error}
		</p>
	{/if}

	<!-- List -->
	{#if data.items.length === 0}
		<p
			data-testid="users-empty"
			class="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground"
		>
			No users on this page.
		</p>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-border">
			<table data-testid="users-table" class="w-full text-left text-sm">
				<thead class="border-b border-border bg-muted/50 text-muted-foreground">
					<tr>
						<th class="px-4 py-2 font-medium">Email</th>
						<th class="px-4 py-2 font-medium">Full name</th>
						<th class="px-4 py-2 font-medium">Active</th>
						<th class="px-4 py-2 font-medium">Superuser</th>
						<th class="px-4 py-2 font-medium">Actions</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-border">
					{#each data.items as u (u.id)}
						<tr data-testid="user-row" data-user-id={u.id}>
							<td class="px-4 py-2 font-medium text-foreground">{u.email}</td>
							<td class="px-4 py-2 text-muted-foreground">{u.full_name ?? '—'}</td>
							<td class="px-4 py-2">
								<span data-testid="user-active">{u.is_active ? 'Yes' : 'No'}</span>
							</td>
							<td class="px-4 py-2">
								<span data-testid="user-superuser">{u.is_superuser ? 'Yes' : 'No'}</span>
							</td>
							<td class="px-4 py-2">
								<div class="flex items-center gap-3">
									<a
										href={`/admin/users/${u.id}`}
										data-testid="edit-user"
										class="text-primary hover:underline">Edit</a
									>
									<form method="POST" action="?/delete" use:enhance>
										<input type="hidden" name="user_id" value={u.id} />
										<button
											type="submit"
											data-testid="delete-user"
											class="text-destructive hover:underline">Delete</button
										>
									</form>
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	{#if shouldShowPagination(data.page, data.limit, data.count)}
		<Pagination {state} />
	{/if}
</section>
