import { error, fail, redirect } from '@sveltejs/kit';
import { requestUpstream, serverApiClient } from '$lib/api/client';
import type { Actions, PageServerLoad } from './$types';

interface UpdateValues {
	email: string;
	full_name: string;
	is_active: boolean;
	is_superuser: boolean;
}

interface UpdateResult {
	formError?: string;
	fieldErrors?: { email?: string };
	values?: UpdateValues;
}

/** Prefill the edit form from `GET /users/{user_id}`. Unknown id → not-found. */
export const load: PageServerLoad = async ({ locals, params, fetch }) => {
	const client = serverApiClient(locals, fetch);
	const { data, response } = await requestUpstream(
		client.GET('/api/v1/users/{user_id}', { params: { path: { user_id: params.id } } })
	);
	if (response.status === 404 || response.status === 422) {
		error(404, 'User not found');
	}
	if (!response.ok || !data) {
		error(502, 'Could not load the user');
	}
	return { editUser: data };
};

export const actions = {
	update: async ({ request, locals, params, fetch }) => {
		const form = await request.formData();
		const values: UpdateValues = {
			email: String(form.get('email') ?? '').trim(),
			full_name: String(form.get('full_name') ?? '').trim(),
			is_active: form.get('is_active') != null,
			is_superuser: form.get('is_superuser') != null
		};
		const password = String(form.get('password') ?? '');

		// UserUpdate requires is_active + is_superuser (both always sent); email and
		// full_name are optional; password only when the superuser typed a new one.
		const body = {
			email: values.email || null,
			full_name: values.full_name || null,
			is_active: values.is_active,
			is_superuser: values.is_superuser,
			...(password ? { password } : {})
		};

		const client = serverApiClient(locals, fetch);
		const { response } = await client.PATCH('/api/v1/users/{user_id}', {
			params: { path: { user_id: params.id } },
			body
		});

		if (response.status === 409) {
			const conflict: UpdateResult = {
				fieldErrors: { email: 'That email is already in use.' },
				values
			};
			return fail(409, conflict);
		}
		if (response.status === 404) {
			const gone: UpdateResult = { formError: 'This user no longer exists.' };
			return fail(404, gone);
		}
		if (!response.ok) {
			const upstream: UpdateResult = {
				formError: 'Could not save the user. Please check the values and try again.',
				values
			};
			return fail(response.status === 422 ? 422 : 502, upstream);
		}

		redirect(303, '/admin/users');
	}
} satisfies Actions;
