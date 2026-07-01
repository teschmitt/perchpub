<script lang="ts">
	import ClassifyStatusBadge from '$lib/components/classify-status-badge.svelte';
	import Pagination from '$lib/components/pagination.svelte';
	import { formatDate } from '$lib/format';
	import { paginate, shouldShowPagination } from '$lib/pagination';
	import type { components } from '$lib/api/schema';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const STATUSES: components['schemas']['ClassifyTaskStatus'][] = [
		'Prepared',
		'Queued',
		'Processing',
		'Success',
		'Failed'
	];
	const state = $derived(paginate(data.page, data.limit, data.count));
</script>

<svelte:head>
	<title>Classify tasks · PerchPub</title>
</svelte:head>

<section class="space-y-6">
	<h1 class="text-2xl font-semibold text-foreground">Classify tasks</h1>

	<!-- Filters navigate via URL search params (GET form); the load reads them. -->
	<form method="GET" data-testid="classify-filters" class="flex flex-wrap items-end gap-3">
		<label class="flex flex-col gap-1 text-sm font-medium" for="status">
			Status
			<select
				id="status"
				name="status"
				data-testid="filter-status"
				class="rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			>
				<option value="" selected={data.statusFilter === null}>All</option>
				{#each STATUSES as s (s)}
					<option value={s} selected={data.statusFilter === s}>{s}</option>
				{/each}
			</select>
		</label>
		<label class="flex flex-col gap-1 text-sm font-medium" for="observation">
			Observation ID
			<input
				id="observation"
				name="observation"
				type="text"
				data-testid="filter-observation"
				value={data.observationFilter ?? ''}
				class="min-w-72 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
			/>
		</label>
		<button
			type="submit"
			data-testid="filter-apply"
			class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			Apply
		</button>
	</form>

	{#if data.items.length === 0}
		<p
			data-testid="classify-empty"
			class="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground"
		>
			No classify tasks match.
		</p>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-border">
			<table data-testid="classify-table" class="w-full text-left text-sm">
				<thead class="border-b border-border bg-muted/50 text-muted-foreground">
					<tr>
						<th class="px-4 py-2 font-medium">Status</th>
						<th class="px-4 py-2 font-medium">Object</th>
						<th class="px-4 py-2 font-medium">Observation</th>
						<th class="px-4 py-2 font-medium">Created</th>
						<th class="px-4 py-2 font-medium">Updated</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-border">
					{#each data.items as task (task.id)}
						<tr data-testid="classify-row">
							<td class="px-4 py-2"><ClassifyStatusBadge status={task.status} /></td>
							<td class="px-4 py-2 font-mono text-xs text-muted-foreground">{task.object_name}</td>
							<td class="px-4 py-2">
								{#if task.observation}
									<a
										href={`/observations/${task.observation.id}`}
										data-testid="classify-observation-link"
										class="text-primary hover:underline">View</a
									>
								{:else}
									<span class="text-muted-foreground">—</span>
								{/if}
							</td>
							<td class="px-4 py-2 text-muted-foreground">{formatDate(task.created_at)}</td>
							<td class="px-4 py-2 text-muted-foreground">{formatDate(task.updated_at)}</td>
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
