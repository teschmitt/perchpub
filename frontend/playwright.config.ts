import { defineConfig } from '@playwright/test';

const PORT = 4173;

export default defineConfig({
	testDir: 'e2e',
	testMatch: '**/*.e2e.{ts,js}',
	use: { baseURL: `http://localhost:${PORT}` },
	webServer: {
		// Preview the production (SSR) build so tests exercise server rendering,
		// hooks, and the BFF cookie flow — closest to the adapter-node prod server.
		command: 'npm run build && npm run preview',
		port: PORT,
		reuseExistingServer: !process.env.CI,
		env: {
			// Server-side data access. In the compose `playwright` service this is
			// http://backend:8000; defaults to the host dev backend otherwise.
			INTERNAL_API_URL: process.env.INTERNAL_API_URL ?? 'http://localhost:8000'
		}
	}
});
