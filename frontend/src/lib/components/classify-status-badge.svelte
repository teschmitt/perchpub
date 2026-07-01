<script lang="ts">
	import { classifyBadgeClass, classifyStatusBadge } from '$lib/classify';
	import type { components } from '$lib/api/schema';

	type ClassifyTaskStatus = components['schemas']['ClassifyTaskStatus'];

	let { status }: { status: ClassifyTaskStatus } = $props();

	const badge = $derived(classifyStatusBadge(status));
</script>

<span
	data-testid="classify-status"
	data-status={status}
	class={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classifyBadgeClass(badge.variant)}`}
>
	{badge.label}
</span>
