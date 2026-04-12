import { expect, test } from '@playwright/test';

import { ensurePlaywrightEnvLoaded, getRequiredModelIds } from './helpers/env';
import { ChatPage } from './pages/chat-page';

ensurePlaywrightEnvLoaded();

const modelIds = getRequiredModelIds();

for (const modelId of modelIds) {
	test(`sends a message with model "${modelId}"`, async ({ page }) => {
		const chatPage = new ChatPage(page);
		const prompt = 'Say hello in one short sentence.';

		await chatPage.goto();
		await chatPage.selectModelById(modelId);
		await chatPage.sendMessage(prompt);
		await chatPage.waitForResponseComplete();

		const assistantMessage = await chatPage.getLastAssistantMessageText();
		expect(assistantMessage.trim().length).toBeGreaterThan(0);
	});
}
