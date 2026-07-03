<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
</script>

<svelte:head>
	<title>Dashboard · PerchPub</title>
</svelte:head>

<section data-testid="dashboard" class="space-y-6">
	<h1 class="text-2xl font-semibold text-foreground">Dashboard</h1>

	{#if data.stationCount === 0}
		<!-- Standing post-signup recommendation until the user owns a working station. -->
		<div
			data-testid="onboarding-hero"
			class="rounded-xl border border-primary/30 bg-primary/5 p-8 text-center"
		>
			<h2 class="text-xl font-semibold text-foreground">Set up your first station</h2>
			<p class="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
				A PerchPub station is a Raspberry Pi at your feeder. Set one up to start capturing and
				classifying visitors.
			</p>
			<a
				href="/stations/new"
				data-testid="setup-first-station"
				class="mt-5 inline-block rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90"
			>
				Set up your first station
			</a>
		</div>
	{:else}
		<p class="text-muted-foreground">Welcome to the PerchPub console.</p>
		<ul class="grid gap-3 sm:grid-cols-2">
			<li>
				<a
					href="/stations/mine"
					class="block rounded-lg border border-border p-4 hover:border-primary hover:shadow-sm"
				>
					<span class="font-medium text-foreground">My stations</span>
					<span class="mt-1 block text-sm text-muted-foreground">View and edit your feeders.</span>
				</a>
			</li>
			<li>
				<a
					href="/account"
					class="block rounded-lg border border-border p-4 hover:border-primary hover:shadow-sm"
				>
					<span class="font-medium text-foreground">Account</span>
					<span class="mt-1 block text-sm text-muted-foreground">Profile, password, and more.</span>
				</a>
			</li>
		</ul>
	{/if}
</section>
