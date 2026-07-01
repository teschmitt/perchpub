<svelte:head>
	<title>Dashboard · PerchPub</title>
</svelte:head>

<section data-testid="dashboard" class="space-y-4">
	<h1 class="text-2xl font-semibold text-foreground">Dashboard</h1>
	<p class="text-muted-foreground">Welcome to the PerchPub console.</p>
	<ul class="grid gap-3 sm:grid-cols-3">
		<li>
			<a
				href="/stations/mine"
				class="block rounded-lg border border-border p-4 hover:border-primary hover:shadow-sm"
			>
				<span class="font-medium text-foreground">My stations</span>
				<span class="mt-1 block text-sm text-muted-foreground">Create and edit your feeders.</span>
			</a>
		</li>
		<li>
			<a
				href="/enroll"
				class="block rounded-lg border border-border p-4 hover:border-primary hover:shadow-sm"
			>
				<span class="font-medium text-foreground">Enroll a device</span>
				<span class="mt-1 block text-sm text-muted-foreground">Pair a new Raspberry Pi.</span>
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
</section>
