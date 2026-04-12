import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

import { expect, test, type Locator, type Page } from '@playwright/test';

import {
	ensurePlaywrightEnvLoaded,
	getAuthStorageStatePath,
	getSsoCredentials,
	getSsoProviderLabel
} from '../helpers/env';
import { ChatPage } from '../pages/chat-page';

ensurePlaywrightEnvLoaded();

const isVisible = async (locator: Locator, timeout = 5_000) =>
	locator.isVisible({ timeout }).catch(() => false);

const clickIfVisible = async (locator: Locator, timeout = 5_000) => {
	if (!(await isVisible(locator, timeout))) {
		return false;
	}

	await locator.click();
	return true;
};

const maybeChooseExistingAccount = async (page: Page, email: string) => {
	const accountLocator = page.getByText(email, { exact: false }).first();
	if (await clickIfVisible(accountLocator, 4_000)) {
		return;
	}

	await clickIfVisible(page.getByText(/Use another account/i).first(), 2_000);
};

const maybeSubmitEmail = async (page: Page, email: string) => {
	const emailInput = page.locator('input[type="email"], input[name="loginfmt"]').first();
	if (!(await isVisible(emailInput, 10_000))) {
		return;
	}

	await emailInput.fill(email);

	const nextButton = page
		.locator('#idSIButton9')
		.or(page.getByRole('button', { name: /^Next$/i }))
		.first();
	await nextButton.click();
};

const maybeSubmitPassword = async (page: Page, password: string) => {
	const passwordInput = page.locator('input[type="password"]').first();
	if (!(await isVisible(passwordInput, 10_000))) {
		return;
	}

	await passwordInput.fill(password);

	const signInButton = page
		.locator('#idSIButton9')
		.or(page.getByRole('button', { name: /^Sign in$/i }))
		.first();
	await signInButton.click();
};

const maybeHandleStaySignedInPrompt = async (page: Page) => {
	await clickIfVisible(page.locator('#idBtn_Back').first(), 5_000);
	await clickIfVisible(page.getByRole('button', { name: /^No$/i }).first(), 2_000);
};

const clickProviderButton = async (page: Page) => {
	const configuredLabel = getSsoProviderLabel();
	const candidates = [
		page.getByRole('button', { name: configuredLabel }).first(),
		page.getByRole('button', { name: /Continue with Microsoft/i }).first(),
		page.getByRole('button', { name: /Microsoft/i }).first()
	];

	for (const candidate of candidates) {
		if (await isVisible(candidate, 5_000)) {
			await candidate.click();
			return;
		}
	}

	throw new Error(
		`Unable to find a Microsoft SSO button on /auth. Checked "${configuredLabel}" and common Microsoft labels.`
	);
};

test('authenticate with Microsoft SSO', async ({ page, context }) => {
	const { email, password } = getSsoCredentials();
	const authStorageStatePath = getAuthStorageStatePath();
	const chatPage = new ChatPage(page);

	await page.addInitScript(() => {
		window.localStorage.setItem('locale', 'en-US');
	});

	await page.goto('/auth');

	if (!(await isVisible(page.locator('#chat-search'), 3_000))) {
		await clickProviderButton(page);
		await maybeChooseExistingAccount(page, email);
		await maybeSubmitEmail(page, email);
		await maybeSubmitPassword(page, password);
		await maybeHandleStaySignedInPrompt(page);
	}

	await expect(page.locator('#chat-search')).toBeVisible({ timeout: 120_000 });
	await chatPage.dismissChangelogIfPresent();

	mkdirSync(dirname(authStorageStatePath), { recursive: true });
	await context.storageState({ path: authStorageStatePath });
});
