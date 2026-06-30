// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
import type { components } from '$lib/api/schema';

declare global {
	namespace App {
		// interface Error {}
		interface Locals {
			/** Raw session JWT from the `pp_session` cookie, or null when anonymous. */
			session: string | null;
			/** Current user resolved per-request via `/users/me`, or null when anonymous. */
			user: components['schemas']['UserPublic'] | null;
		}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
