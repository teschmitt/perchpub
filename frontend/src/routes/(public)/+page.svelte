<svelte:head>
	<title>PerchPub — backyard bird-feeder observations</title>
	<meta
		name="description"
		content="PerchPub is a self-hosted bird-feeder observation server: Raspberry Pi stations capture feeder visits, classify the species, and share the observations."
	/>
</svelte:head>

<section data-testid="landing" class="flex flex-col items-start gap-4 py-12">
	<h1 class="text-4xl font-bold tracking-tight text-foreground">PerchPub</h1>
	<p class="max-w-2xl text-lg text-muted-foreground">
		A self-hosted bird-feeder observation server. Stations at the feeder capture photos and short
		videos, classify the visiting species, and publish the observations here.
	</p>
	<div class="flex gap-3">
		<a
			href="/observations"
			class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
		>
			Browse observations
		</a>
		<a
			href="/species"
			class="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent"
		>
			Species catalog
		</a>
	</div>
</section>
