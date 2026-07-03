<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { LayoutData } from './$types';
	import SiteFooter from '$lib/components/site-footer.svelte';

	let { data, children }: { data: LayoutData; children: Snippet } = $props();
</script>

<div class="flex min-h-screen bg-background text-foreground">
	<aside class="w-56 shrink-0 border-r border-sidebar-border bg-sidebar p-4">
		<a href="/" class="mb-6 block text-lg font-semibold text-primary">PerchPub</a>
		<nav class="flex flex-col gap-1 text-sm">
			<a href="/dashboard" class="rounded-md px-2 py-1.5 hover:bg-accent">Dashboard</a>
			<a
				href="/stations/mine"
				data-testid="nav-stations"
				class="rounded-md px-2 py-1.5 hover:bg-accent">My stations</a
			>
			<a href="/account" data-testid="nav-account" class="rounded-md px-2 py-1.5 hover:bg-accent"
				>Account</a
			>
			{#if data.user.is_superuser}
				<div class="mt-4 flex flex-col gap-1 border-t border-sidebar-border pt-4">
					<p
						class="px-2 pb-0.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
					>
						Admin
					</p>
					<a
						href="/admin/users"
						data-testid="nav-admin-users"
						class="rounded-md px-2 py-1.5 hover:bg-accent">Users</a
					>
					<a
						href="/admin/classify-tasks"
						data-testid="nav-admin-classify-tasks"
						class="rounded-md px-2 py-1.5 hover:bg-accent">Classify tasks</a
					>
					<a
						href="/admin/ops"
						data-testid="nav-admin-ops"
						class="rounded-md px-2 py-1.5 hover:bg-accent">Ops</a
					>
				</div>
			{/if}
		</nav>
	</aside>
	<div class="flex flex-1 flex-col">
		<header class="flex items-center justify-between border-b border-border px-6 py-3">
			<span class="text-sm text-muted-foreground">{data.user.email}</span>
			<form method="POST" action="/logout">
				<button type="submit" data-testid="logout" class="text-sm hover:text-primary">
					Log out
				</button>
			</form>
		</header>
		<main class="flex-1 p-6">
			{@render children()}
		</main>
		<SiteFooter />
	</div>
</div>
