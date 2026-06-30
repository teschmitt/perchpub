import { redirect, type RequestHandler } from '@sveltejs/kit';
import { SESSION_COOKIE } from '$lib/server/auth';

function clearAndRedirect(cookies: import('@sveltejs/kit').Cookies): never {
	cookies.delete(SESSION_COOKIE, { path: '/' });
	redirect(303, '/');
}

export const POST: RequestHandler = ({ cookies }) => clearAndRedirect(cookies);

// Convenience for a plain logout link (clearing your own cookie is harmless).
export const GET: RequestHandler = ({ cookies }) => clearAndRedirect(cookies);
