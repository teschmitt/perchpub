<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: Snippet } = $props();
</script>

<div class="flex min-h-screen flex-col bg-background text-foreground">
	<header class="border-b border-border">
		<nav class="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
			<a href="/" class="text-lg font-semibold text-primary">PerchPub</a>
			<ul class="flex items-center gap-4 text-sm">
				<li><a href="/observations" class="hover:text-primary">Observations</a></li>
				<li><a href="/species" class="hover:text-primary">Species</a></li>
				<li><a href="/stations" class="hover:text-primary">Stations</a></li>
				<li>
					{#if data.user}
						<a
							href="/dashboard"
							data-testid="nav-account"
							class="rounded-md bg-primary px-3 py-1.5 text-primary-foreground"
						>
							Account
						</a>
					{:else}
						<a
							href="/login"
							data-testid="nav-login"
							class="rounded-md bg-primary px-3 py-1.5 text-primary-foreground"
						>
							Login
						</a>
					{/if}
				</li>
			</ul>
		</nav>
	</header>
	<main class="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
		{@render children()}
	</main>
</div>
