import { basename } from 'node:path';

import { expect, type Page } from '@playwright/test';

export class ChatPage {
	private readonly page: Page;

	private localePrepared = false;

	constructor(page: Page) {
		this.page = page;
	}

	private async ensureEnglishLocale() {
		if (this.localePrepared) {
			return;
		}

		await this.page.addInitScript(() => {
			window.localStorage.setItem('locale', 'en-US');
		});

		this.localePrepared = true;
	}

	async goto() {
		await this.ensureEnglishLocale();
		await this.page.goto('/');
		await expect(this.page.locator('#chat-search')).toBeVisible({ timeout: 60_000 });
		await this.dismissChangelogIfPresent();
	}

	async dismissChangelogIfPresent() {
		const changelogButton = this.page.getByRole('button', {
			name: "Okay, Let's Go!"
		});

		if (await changelogButton.isVisible({ timeout: 2_000 }).catch(() => false)) {
			await changelogButton.click();
		}
	}

	async selectModelById(modelId: string) {
		const selectorButton = this.page
			.locator('button[id^="model-selector-"][id$="-button"]')
			.first();

		await expect(selectorButton).toBeVisible({ timeout: 30_000 });
		await selectorButton.click();

		const searchInput = this.page.locator('#model-search-input');
		if (await searchInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
			await searchInput.fill(modelId);
		}

		const option = this.page.locator(`button[data-value="${modelId}"]`).first();
		await expect(option).toBeVisible({ timeout: 15_000 });
		await option.click();
		await expect(searchInput).toBeHidden({ timeout: 15_000 });
	}

	async sendMessage(prompt: string) {
		const input = this.page.locator('#chat-input');
		const sendButton = this.page.locator('#send-message-button');

		await expect(input).toBeVisible({ timeout: 30_000 });
		await input.click();
		await input.fill(prompt);
		await expect(sendButton).toBeEnabled({ timeout: 15_000 });
		await sendButton.click();
	}

	async attachFile(filePath: string) {
		const fileInput = this.page.locator('input[type="file"]').first();
		const sendButton = this.page.locator('#send-message-button');

		await fileInput.setInputFiles(filePath);
		await expect(this.page.getByText(basename(filePath), { exact: false })).toBeVisible({
			timeout: 60_000
		});
		await expect(sendButton).toBeEnabled({ timeout: 60_000 });
	}

	async waitForResponseComplete(timeout = 120_000) {
		await expect(this.page.locator('.chat-user').last()).toBeVisible({ timeout });
		await expect(this.page.locator('.chat-assistant').last()).toBeVisible({ timeout });
		await expect(this.page.locator('div[aria-label="Generation Info"]').last()).toBeVisible({
			timeout
		});
	}

	async waitForCitationToggle(timeout = 60_000) {
		await expect(this.page.locator('button[aria-label^="Toggle "]').last()).toBeVisible({
			timeout
		});
	}

	async getLastAssistantMessageText() {
		return this.page.locator('.chat-assistant').last().innerText();
	}
}
