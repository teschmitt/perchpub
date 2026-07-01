import type { APIRequestContext, Page } from '@playwright/test';

/**
 * Backend origin for seeding fixtures. The Playwright process talks to the SAME
 * backend the SSR server reaches (compose `playwright` → http://backend:8000;
 * host dev → http://localhost:8000). Relative `request.get('/...')` calls still
 * hit the frontend via the configured baseURL.
 */
export const API_URL = process.env.INTERNAL_API_URL ?? 'http://localhost:8000';

const EMAIL = process.env.FIRST_SUPERUSER ?? 'admin@example.com';
const PASSWORD = process.env.FIRST_SUPERUSER_PASSWORD ?? 'changethis';

/** Log in via the backend OAuth2 password grant and return the access token. */
export async function apiLoginAs(
	request: APIRequestContext,
	email: string,
	password: string
): Promise<string> {
	const res = await request.post(`${API_URL}/api/v1/login/access-token`, {
		form: { username: email, password }
	});
	if (!res.ok()) {
		throw new Error(`login failed: ${res.status()} ${await res.text()}`);
	}
	const body = (await res.json()) as { access_token: string };
	return body.access_token;
}

/** Log in as the seeded superuser and return the access token. */
export function apiLogin(request: APIRequestContext): Promise<string> {
	return apiLoginAs(request, EMAIL, PASSWORD);
}

/** A per-run unique email so signup always creates a fresh account. */
export function uniqueEmail(prefix = 'owner'): string {
	return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

/**
 * Register a fresh (active, non-superuser) account via the public signup endpoint.
 * Returns the credentials so a test can then log in through the UI. Used by the
 * account/owner flows so they never mutate the shared superuser.
 */
export async function signupUser(
	request: APIRequestContext,
	email: string,
	password: string,
	fullName?: string
): Promise<{ email: string; password: string }> {
	const res = await request.post(`${API_URL}/api/v1/users/signup`, {
		data: { email, password, full_name: fullName ?? null }
	});
	if (!res.ok()) {
		throw new Error(`signup failed: ${res.status()} ${await res.text()}`);
	}
	return { email, password };
}

/** Log in through the BFF UI form; lands on the dashboard with the session cookie set. */
export async function uiLogin(page: Page, email: string, password: string): Promise<void> {
	await page.goto('/login');
	await page.getByTestId('email-input').fill(email);
	await page.getByTestId('password-input').fill(password);
	await page.getByRole('button', { name: 'Log In' }).click();
	await page.waitForURL('**/dashboard');
}

/** Log in through the UI as the seeded superuser. */
export function uiLoginSuperuser(page: Page): Promise<void> {
	return uiLogin(page, EMAIL, PASSWORD);
}

export interface StationSeed {
	latitude: number;
	longitude: number;
	is_private: boolean;
}

/** Create a station owned by the authenticated caller; returns the created row. */
export async function createStation(
	request: APIRequestContext,
	token: string,
	station: StationSeed
): Promise<{ id: string }> {
	const res = await request.post(`${API_URL}/api/v1/station/`, {
		headers: { Authorization: `Bearer ${token}` },
		data: station
	});
	if (!res.ok()) {
		throw new Error(`createStation failed: ${res.status()} ${await res.text()}`);
	}
	return (await res.json()) as { id: string };
}

export interface ObservationSeed {
	station_id: string;
	object_name: string;
	observed_at: string;
	confidence_score: number | null;
	latitude: number;
	longitude: number;
	species_id?: string | null;
}

/** Create a species (superuser-only). Returns the created row. */
export async function createSpecies(
	request: APIRequestContext,
	token: string,
	species: { scientific_name: string; classification_id: number }
): Promise<{ id: string; scientific_name: string }> {
	const res = await request.post(`${API_URL}/api/v1/species/`, {
		headers: { Authorization: `Bearer ${token}` },
		data: species
	});
	if (!res.ok()) {
		throw new Error(`createSpecies failed: ${res.status()} ${await res.text()}`);
	}
	return (await res.json()) as { id: string; scientific_name: string };
}

/** Create an observation. The bearer is sent defensively (harmless if optional). */
export async function createObservation(
	request: APIRequestContext,
	token: string,
	observation: ObservationSeed
): Promise<{ id: string }> {
	const res = await request.post(`${API_URL}/api/v1/observation/`, {
		headers: { Authorization: `Bearer ${token}` },
		data: { classification_result: null, ...observation }
	});
	if (!res.ok()) {
		throw new Error(`createObservation failed: ${res.status()} ${await res.text()}`);
	}
	return (await res.json()) as { id: string };
}
