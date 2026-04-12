import { expect, test } from '@playwright/test';

import {
	ensurePlaywrightEnvLoaded,
	getOptionalRagFilePath,
	getRequiredRagModelId
} from './helpers/env';
import { ChatPage } from './pages/chat-page';

ensurePlaywrightEnvLoaded();

const ragModelId = getRequiredRagModelId();
const ragFilePath = getOptionalRagFilePath();

test('uploads a file and shows citations for a RAG response', async ({ page }) => {
	test.skip(
		!ragFilePath,
		'Add a file to tests/playwright/fixtures/rag/ or set PLAYWRIGHT_RAG_FILE before running the RAG test.'
	);

	const resolvedFilePath = ragFilePath as string;
	const chatPage = new ChatPage(page);

	await chatPage.goto();
	await chatPage.selectModelById(ragModelId);
	await chatPage.attachFile(resolvedFilePath);
	await chatPage.sendMessage('Summarize the attached document in one short sentence and cite the source.');
	await chatPage.waitForResponseComplete();
	await chatPage.waitForCitationToggle();

	const assistantMessage = await chatPage.getLastAssistantMessageText();
	expect(assistantMessage.trim().length).toBeGreaterThan(0);
});
