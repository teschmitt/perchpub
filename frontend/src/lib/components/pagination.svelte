<script lang="ts">
	import { page } from '$app/state';
	import type { PaginationState } from '$lib/pagination';

	let { state }: { state: PaginationState } = $props();

	/** Build a `?page=N` href that preserves any other query params on the URL. */
	function href(target: number): string {
		const entries = [...page.url.searchParams.entries()].filter(([key]) => key !== 'page');
		entries.push(['page', String(target)]);
		return `?${new URLSearchParams(entries).toString()}`;
	}
</script>

<nav
	aria-label="Pagination"
	data-testid="pagination"
	class="flex items-center justify-between pt-8"
>
	{#if state.hasPrev}
		<a
			data-testid="page-prev"
			href={href(state.prevPage)}
			rel="prev"
			class="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent"
		>
			← Previous
		</a>
	{:else}
		<span
			data-testid="page-prev"
			aria-disabled="true"
			class="cursor-not-allowed rounded-md border border-border px-4 py-2 text-sm font-medium opacity-40"
		>
			← Previous
		</span>
	{/if}

	<span class="text-sm text-muted-foreground">Page {state.page}</span>

	{#if state.hasNext}
		<a
			data-testid="page-next"
			href={href(state.nextPage)}
			rel="next"
			class="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent"
		>
			Next →
		</a>
	{:else}
		<span
			data-testid="page-next"
			aria-disabled="true"
			class="cursor-not-allowed rounded-md border border-border px-4 py-2 text-sm font-medium opacity-40"
		>
			Next →
		</span>
	{/if}
</nav>
