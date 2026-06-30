<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: Snippet } = $props();
</script>

<div class="flex min-h-screen bg-background text-foreground">
	<aside class="w-56 shrink-0 border-r border-sidebar-border bg-sidebar p-4">
		<a href="/" class="mb-6 block text-lg font-semibold text-primary">PerchPub</a>
		<nav class="flex flex-col gap-1 text-sm">
			<a href="/dashboard" class="rounded-md px-2 py-1.5 hover:bg-accent">Dashboard</a>
			<a href="/stations" class="rounded-md px-2 py-1.5 hover:bg-accent">Stations</a>
			<a href="/account" class="rounded-md px-2 py-1.5 hover:bg-accent">Account</a>
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
	</div>
</div>
