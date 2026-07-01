import { fail, redirect } from '@sveltejs/kit';
import { serverApiClient } from '$lib/api/client';
import { SESSION_COOKIE } from '$lib/server/auth';
import type { Actions, PageServerLoad } from './$types';

const MIN_PASSWORD_LENGTH = 8;

interface AccountResult {
	intent: 'profile' | 'password' | 'delete';
	success?: boolean;
	error?: string;
	fieldErrors?: {
		full_name?: string;
		email?: string;
		current_password?: string;
		new_password?: string;
	};
	values?: { full_name?: string; email?: string };
}

export const load: PageServerLoad = async ({ locals }) => {
	// The (app) guard guarantees a user; expose it for the form defaults and the
	// superuser-gated delete control.
	return { user: locals.user! };
};

export const actions = {
	updateProfile: async ({ request, locals, fetch }) => {
		const form = await request.formData();
		const full_name = String(form.get('full_name') ?? '').trim();
		const email = String(form.get('email') ?? '').trim();

		const client = serverApiClient(locals, fetch);
		const { response } = await client.PATCH('/api/v1/users/me', { body: { full_name, email } });

		if (response.status === 409) {
			const result: AccountResult = {
				intent: 'profile',
				fieldErrors: { email: 'That email is already in use.' },
				values: { full_name, email }
			};
			return fail(409, result);
		}
		if (!response.ok) {
			const result: AccountResult = {
				intent: 'profile',
				error: 'Could not update your profile. Please try again.',
				values: { full_name, email }
			};
			return fail(response.status === 422 ? 422 : 502, result);
		}
		const ok: AccountResult = { intent: 'profile', success: true };
		return ok;
	},

	changePassword: async ({ request, locals, fetch }) => {
		const form = await request.formData();
		const current_password = String(form.get('current_password') ?? '');
		const new_password = String(form.get('new_password') ?? '');

		// Mirror UpdatePassword's min_length=8 so the backend 400 paths below are
		// reached with well-formed input (a short value would otherwise 422).
		const fieldErrors: NonNullable<AccountResult['fieldErrors']> = {};
		if (current_password.length < MIN_PASSWORD_LENGTH) {
			fieldErrors.current_password = `Must be at least ${MIN_PASSWORD_LENGTH} characters.`;
		}
		if (new_password.length < MIN_PASSWORD_LENGTH) {
			fieldErrors.new_password = `Must be at least ${MIN_PASSWORD_LENGTH} characters.`;
		}
		if (fieldErrors.current_password || fieldErrors.new_password) {
			return fail(400, { intent: 'password', fieldErrors } satisfies AccountResult);
		}

		const client = serverApiClient(locals, fetch);
		// openapi-fetch returns the parsed error body on `error` for non-2xx.
		const { error: errorBody, response } = await client.PATCH('/api/v1/users/me/password', {
			body: { current_password, new_password }
		});

		if (response.status === 400) {
			const rawDetail = (errorBody as { detail?: unknown } | undefined)?.detail;
			const detail = typeof rawDetail === 'string' ? rawDetail : '';
			const result: AccountResult = { intent: 'password' };
			if (/same as the current/i.test(detail)) {
				result.fieldErrors = { new_password: 'New password cannot match the current one.' };
			} else {
				result.fieldErrors = { current_password: 'Incorrect password.' };
			}
			return fail(400, result);
		}
		if (!response.ok) {
			const result: AccountResult = {
				intent: 'password',
				error: 'Could not change your password. Please try again.'
			};
			return fail(response.status === 422 ? 422 : 502, result);
		}
		const ok: AccountResult = { intent: 'password', success: true };
		return ok;
	},

	deleteAccount: async ({ request, locals, cookies, fetch }) => {
		const form = await request.formData();
		if (form.get('confirm') == null) {
			return fail(400, {
				intent: 'delete',
				error: 'Please confirm before deleting your account.'
			} satisfies AccountResult);
		}

		const client = serverApiClient(locals, fetch);
		const { response } = await client.DELETE('/api/v1/users/me');

		// The backend forbids superuser self-deletion (403); reflect it without
		// touching the session.
		if (response.status === 403) {
			return fail(403, {
				intent: 'delete',
				error: 'Superusers cannot delete their own account.'
			} satisfies AccountResult);
		}
		if (!response.ok) {
			return fail(502, {
				intent: 'delete',
				error: 'Could not delete your account. Please try again.'
			} satisfies AccountResult);
		}

		// Clear the BFF session (reuse P0's cookie-clearing) and land on the public site.
		cookies.delete(SESSION_COOKIE, { path: '/' });
		redirect(303, '/');
	}
} satisfies Actions;
