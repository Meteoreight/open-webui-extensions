import { defineConfig, devices } from '@playwright/test';

import {
	ensurePlaywrightEnvLoaded,
	getAuthStorageStatePath,
	getBaseUrlOrThrow
} from './tests/playwright/helpers/env';

ensurePlaywrightEnvLoaded();

const baseURL = getBaseUrlOrThrow();
const authStorageStatePath = getAuthStorageStatePath();

export default defineConfig({
	testDir: './tests/playwright',
	timeout: 180_000,
	expect: {
		timeout: 15_000
	},
	retries: process.env.CI ? 1 : 0,
	reporter: [
		['list'],
		['html', { open: 'never' }]
	],
	outputDir: 'test-results',
	use: {
		baseURL,
		trace: 'on-first-retry',
		screenshot: 'only-on-failure',
		video: 'retain-on-failure'
	},
	projects: [
		{
			name: 'setup',
			testMatch: /setup\/auth\.setup\.ts/
		},
		{
			name: 'chromium',
			dependencies: ['setup'],
			use: {
				...devices['Desktop Chrome'],
				storageState: authStorageStatePath
			}
		}
	]
});
