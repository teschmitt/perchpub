import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

/**
 * Station creation and device enrollment are unified into one setup wizard at
 * `/stations/new`. This legacy `/enroll` route permanently redirects there so
 * existing bookmarks and links keep working (308 = moved for good).
 */
export const load: PageServerLoad = () => {
	redirect(308, '/stations/new');
};
