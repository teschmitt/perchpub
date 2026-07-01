<script lang="ts">
	import QRCode from 'qrcode';
	import {
		ENROLL_QR_EC_LEVEL,
		enrollQrSegments,
		formatCountdown,
		isExpired,
		secondsRemaining
	} from '$lib/enrollment';

	let {
		token,
		sessionId,
		caPin,
		expiresAt
	}: { token: string; sessionId: string; caPin: string; expiresAt: string } = $props();

	// Memory-only clock. Never persisted, never placed in a URL/query/store — the
	// token lives only in this component's transient state for its one-time display.
	let now = $state(Date.now());
	const remaining = $derived(secondsRemaining(expiresAt, now));
	const expired = $derived(isExpired(expiresAt, now));

	let copied = $state<'token' | 'session' | null>(null);

	// The scannable QR, rendered in-memory as SVG from the transient session
	// values — the perchstation pairing payload {session_id, auth_token, ca_pin}.
	// Never fetched from a token-bearing URL, never written to a store. EC level M
	// buys robustness for the screen→feeder-camera path; the payload is tiny.
	let qrSvg = $state('');
	$effect(() => {
		const segments = enrollQrSegments({
			session_id: sessionId,
			auth_token: token,
			ca_pin: caPin
		});
		let cancelled = false;
		QRCode.toString(segments, { type: 'svg', errorCorrectionLevel: ENROLL_QR_EC_LEVEL, margin: 4 })
			.then((svg) => {
				if (!cancelled) qrSvg = svg;
			})
			.catch(() => {
				if (!cancelled) qrSvg = '';
			});
		return () => {
			cancelled = true;
		};
	});

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
		Point the feeder camera at this QR code to pair the Raspberry Pi before the timer runs out. This
		code is shown only once.
	</p>

	{#if expired}
		<div
			data-testid="enroll-qr-expired"
			class="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
		>
			This enrollment code has expired. Start a new session to try again.
		</div>
	{:else}
		<div class="flex justify-center">
			<div
				data-testid="enroll-qr"
				class="rounded-lg bg-white p-3 [&_svg]:h-56 [&_svg]:w-56"
				aria-label="Enrollment QR code"
			>
				<!-- eslint-disable-next-line svelte/no-at-html-tags -- trusted, in-memory library SVG -->
				{@html qrSvg}
			</div>
		</div>
	{/if}

	<details data-testid="enroll-manual" class="rounded-md border border-border">
		<summary
			data-testid="enroll-manual-toggle"
			class="cursor-pointer px-3 py-2 text-sm font-medium text-foreground"
		>
			Can't scan? Enter the credentials manually
		</summary>

		<div class="space-y-4 border-t border-border p-3">
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
	</details>
</div>
