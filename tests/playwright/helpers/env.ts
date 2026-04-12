import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, isAbsolute, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const helperDirectory = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(helperDirectory, '../../..');
const authStorageStatePath = resolve(projectRoot, 'tests/playwright/.auth/user.json');
const ragFixtureDirectory = resolve(projectRoot, 'tests/playwright/fixtures/rag');
const envFiles = [
	resolve(projectRoot, '.env.playwright'),
	resolve(projectRoot, '.env.playwright.local')
];

let envLoaded = false;

const stripWrappingQuotes = (value: string) => {
	if (
		(value.startsWith('"') && value.endsWith('"')) ||
		(value.startsWith("'") && value.endsWith("'"))
	) {
		return value.slice(1, -1);
	}

	return value;
};

const parseEnvLine = (line: string) => {
	const trimmed = line.trim();

	if (trimmed === '' || trimmed.startsWith('#')) {
		return null;
	}

	const normalized = trimmed.startsWith('export ') ? trimmed.slice(7).trim() : trimmed;
	const separatorIndex = normalized.indexOf('=');

	if (separatorIndex === -1) {
		return null;
	}

	const key = normalized.slice(0, separatorIndex).trim();
	const value = stripWrappingQuotes(normalized.slice(separatorIndex + 1).trim());

	if (!key) {
		return null;
	}

	return { key, value };
};

export const ensurePlaywrightEnvLoaded = () => {
	if (envLoaded) {
		return;
	}

	for (const envFile of envFiles) {
		if (!existsSync(envFile)) {
			continue;
		}

		const contents = readFileSync(envFile, 'utf8');

		for (const line of contents.split(/\r?\n/u)) {
			const parsed = parseEnvLine(line);

			if (!parsed || process.env[parsed.key] !== undefined) {
				continue;
			}

			process.env[parsed.key] = parsed.value;
		}
	}

	envLoaded = true;
};

const getRequiredEnv = (name: string) => {
	ensurePlaywrightEnvLoaded();

	const value = process.env[name]?.trim();

	if (!value) {
		throw new Error(
			`Missing required environment variable ${name}. Add it to .env.playwright or export it before running Playwright.`
		);
	}

	return value;
};

export const getAuthStorageStatePath = () => {
	ensurePlaywrightEnvLoaded();
	return authStorageStatePath;
};

export const getBaseUrlOrThrow = () => {
	const baseUrl = getRequiredEnv('PLAYWRIGHT_BASE_URL');

	try {
		new URL(baseUrl);
	} catch {
		throw new Error(
			`PLAYWRIGHT_BASE_URL must be a valid absolute URL. Received: ${baseUrl}`
		);
	}

	return baseUrl;
};

export const getRequiredModelIds = () => {
	const modelIds = getRequiredEnv('PLAYWRIGHT_MODEL_IDS')
		.split(',')
		.map((modelId) => modelId.trim())
		.filter(Boolean);

	if (modelIds.length === 0) {
		throw new Error(
			'PLAYWRIGHT_MODEL_IDS must contain at least one comma-separated model id.'
		);
	}

	return [...new Set(modelIds)];
};

export const getRequiredRagModelId = () => getRequiredEnv('PLAYWRIGHT_RAG_MODEL_ID');

export const getSsoCredentials = () => ({
	email: getRequiredEnv('PLAYWRIGHT_SSO_EMAIL'),
	password: getRequiredEnv('PLAYWRIGHT_SSO_PASSWORD')
});

export const getSsoProviderLabel = () =>
	process.env.PLAYWRIGHT_SSO_PROVIDER_LABEL?.trim() || 'Sign in with Microsoft';

const resolvePathFromProjectRoot = (filePath: string) =>
	isAbsolute(filePath) ? filePath : resolve(projectRoot, filePath);

export const getOptionalRagFilePath = () => {
	ensurePlaywrightEnvLoaded();

	const explicitPath = process.env.PLAYWRIGHT_RAG_FILE?.trim();

	if (explicitPath) {
		const resolvedPath = resolvePathFromProjectRoot(explicitPath);

		if (!existsSync(resolvedPath)) {
			throw new Error(
				`PLAYWRIGHT_RAG_FILE points to a missing file: ${resolvedPath}`
			);
		}

		return resolvedPath;
	}

	if (!existsSync(ragFixtureDirectory)) {
		return null;
	}

	const fixtureFile = readdirSync(ragFixtureDirectory, { withFileTypes: true })
		.filter((entry) => entry.isFile() && !entry.name.startsWith('.'))
		.map((entry) => resolve(ragFixtureDirectory, entry.name))
		.sort()[0];

	return fixtureFile ?? null;
};
