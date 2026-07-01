import { error, fail, redirect } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import { DEFAULT_LIMIT, parsePage, skipFor } from '$lib/pagination';
import type { Actions, PageServerLoad } from './$types';

/** Read the parsed `{detail}` string from an openapi-fetch error body, if any. */
function detailOf(errorBody: unknown): string | undefined {
	const detail = (errorBody as { detail?: unknown } | undefined)?.detail;
	return typeof detail === 'string' ? detail : undefined;
}

interface CreateValues {
	email: string;
	full_name: string;
	is_active: boolean;
	is_superuser: boolean;
}

interface CreateResult {
	intent: 'create';
	formError?: string;
	values?: CreateValues;
}

interface DeleteResult {
	intent: 'delete';
	error?: string;
}

/**
 * Superuser user list. The `(app)/admin` layout guard has already asserted
 * superuser; the backend `get_current_active_superuser` on `GET /users/` is the
 * defense-in-depth. Paginated over `skip`/`limit` like the other list pages.
 */
export const load: PageServerLoad = async ({ locals, url, fetch }) => {
	const limit = DEFAULT_LIMIT;
	const page = parsePage(url.searchParams);
	const skip = skipFor(page, limit);

	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/users/', { params: { query: { skip, limit } } })
	);
	if (!response.ok || !data) {
		error(502, 'Could not load users');
	}
	return { items: data.data, count: data.count, page, limit };
};

export const actions = {
	create: async ({ request, locals, fetch }) => {
		const form = await request.formData();
		const values: CreateValues = {
			email: String(form.get('email') ?? '').trim(),
			full_name: String(form.get('full_name') ?? '').trim(),
			is_active: form.get('is_active') != null,
			is_superuser: form.get('is_superuser') != null
		};
		const password = String(form.get('password') ?? '');

		const client = serverApiClient(locals, fetch);
		const { error: errorBody, response } = await client.POST('/api/v1/users/', {
			body: {
				email: values.email,
				password,
				full_name: values.full_name || null,
				is_active: values.is_active,
				is_superuser: values.is_superuser
			}
		});

		// 400 = duplicate email; surface the backend's own message verbatim.
		if (response.status === 400) {
			const dup: CreateResult = {
				intent: 'create',
				formError: detailOf(errorBody) ?? 'Could not create the user.',
				values
			};
			return fail(400, dup);
		}
		if (!response.ok) {
			const upstream: CreateResult = {
				intent: 'create',
				formError: 'Could not create the user. Please check the values and try again.',
				values
			};
			return fail(response.status === 422 ? 422 : 502, upstream);
		}

		redirect(303, '/admin/users');
	},

	delete: async ({ request, locals, fetch }) => {
		const form = await request.formData();
		const user_id = String(form.get('user_id') ?? '');

		const client = serverApiClient(locals, fetch);
		const { error: errorBody, response } = await client.DELETE('/api/v1/users/{user_id}', {
			params: { path: { user_id } }
		});

		// 403 = a superuser cannot delete their own row; reflect it, don't crash.
		if (response.status === 403) {
			const forbidden: DeleteResult = {
				intent: 'delete',
				error: detailOf(errorBody) ?? 'You cannot delete this user.'
			};
			return fail(403, forbidden);
		}
		if (!response.ok) {
			const upstream: DeleteResult = { intent: 'delete', error: 'Could not delete the user.' };
			return fail(response.status === 404 ? 404 : 502, upstream);
		}

		redirect(303, '/admin/users');
	}
} satisfies Actions;
