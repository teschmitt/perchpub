<script lang="ts">
	import { formatCountdown, isExpired, secondsRemaining } from '$lib/enrollment';

	let { token, sessionId, expiresAt }: { token: string; sessionId: string; expiresAt: string } =
		$props();

	// Memory-only clock. Never persisted, never placed in a URL/query/store — the
	// token lives only in this component's transient state for its one-time display.
	let now = $state(Date.now());
	const remaining = $derived(secondsRemaining(expiresAt, now));
	const expired = $derived(isExpired(expiresAt, now));

	let copied = $state<'token' | 'session' | null>(null);

	$effect(() => {
		// Tick once per second until the deadline, then stop (referencing `expired`
		// re-runs this effect at expiry so the interval is cleared).
		if (expired) {
			return;
		}
		const id = setInterval(() => {
			now = Date.now();
		}, 1000);
		return () => clearInterval(id);
	});

	async function copy(kind: 'token' | 'session', value: string) {
		try {
			await navigator.clipboard.writeText(value);
			copied = kind;
		} catch {
			copied = null;
		}
	}
</script>

<div
	data-testid="enroll-token"
	class="space-y-4 rounded-lg border border-border bg-card p-5"
	class:opacity-60={expired}
>
	<div class="flex items-center justify-between gap-3">
		<h2 class="text-lg font-semibold text-foreground">Enrollment session started</h2>
		{#if expired}
			<span
				data-testid="token-expired"
				class="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive"
			>
				Expired
			</span>
		{:else}
			<span
				data-testid="countdown"
				class="rounded-full bg-muted px-2 py-0.5 font-mono text-xs font-medium text-muted-foreground"
			>
				{formatCountdown(remaining)}
			</span>
		{/if}
	</div>

	<p class="text-sm text-muted-foreground">
		Run enrollment on the Raspberry Pi with the values below before the timer runs out. This token
		is shown only once.
	</p>

	<div class="space-y-1">
		<span class="text-xs font-medium text-muted-foreground">Session ID</span>
		<div class="flex items-center gap-2">
			<code data-testid="session-id" class="flex-1 truncate rounded bg-muted px-2 py-1 text-sm">
				{sessionId}
			</code>
			<button
				type="button"
				data-testid="copy-session"
				onclick={() => copy('session', sessionId)}
				class="rounded-md border border-input px-2 py-1 text-xs hover:bg-accent"
			>
				{copied === 'session' ? 'Copied' : 'Copy'}
			</button>
		</div>
	</div>

	<div class="space-y-1">
		<span class="text-xs font-medium text-muted-foreground">One-time auth token</span>
		<div class="flex items-center gap-2">
			<code data-testid="auth-token" class="flex-1 truncate rounded bg-muted px-2 py-1 text-sm">
				{token}
			</code>
			<button
				type="button"
				data-testid="copy-token"
				disabled={expired}
				onclick={() => copy('token', token)}
				class="rounded-md border border-input px-2 py-1 text-xs hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
			>
				{copied === 'token' ? 'Copied' : 'Copy'}
			</button>
		</div>
	</div>
</div>
