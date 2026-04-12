# Playwright Test Notes

This directory contains Playwright-based UI smoke tests for an already running Open WebUI instance.

The repository does **not** own the target UI implementation. The tests here are an external client against a deployed or locally running Open WebUI, and the target URL is always provided at runtime through environment variables.

## What These Tests Cover

The current suite is intentionally small and focused on high-signal checks:

- `chat-connectivity.spec.ts`
  - Iterates over `PLAYWRIGHT_MODEL_IDS`
  - Selects each model by exact `model id`
  - Sends a short prompt
  - Waits for a visible assistant response and completion signal

- `rag-attachment.spec.ts`
  - Uses `PLAYWRIGHT_RAG_MODEL_ID`
  - Attaches a file to the chat input
  - Sends a short RAG-oriented prompt
  - Waits for response completion
  - Verifies that the citation/source toggle appears

- `setup/auth.setup.ts`
  - Handles initial authentication through the Microsoft SSO button in the Open WebUI auth page
  - Saves Playwright storage state to `tests/playwright/.auth/user.json`

## Directory Layout

```text
tests/playwright/
├── README.md
├── chat-connectivity.spec.ts
├── rag-attachment.spec.ts
├── fixtures/
│   └── rag/
│       └── .gitkeep
├── helpers/
│   └── env.ts
├── pages/
│   └── chat-page.ts
└── setup/
    └── auth.setup.ts
```

## Runtime Model

These tests assume:

- Open WebUI is already up and reachable
- the URL is passed in through `PLAYWRIGHT_BASE_URL`
- Microsoft SSO is enabled on the target instance
- a test account exists and can sign in through that SSO flow

The suite does **not** start Open WebUI, Docker Compose, or a local dev server.

## Environment Variables

The config and tests read environment values through `helpers/env.ts`.

Required variables:

- `PLAYWRIGHT_BASE_URL`
  - Absolute URL of the target Open WebUI instance
  - The Playwright config fails fast if this is missing or invalid

- `PLAYWRIGHT_MODEL_IDS`
  - Comma-separated model IDs for chat connectivity checks
  - Example: `gpt-4o-mini,my-rag-model`

- `PLAYWRIGHT_RAG_MODEL_ID`
  - Single model ID reserved for the file attachment / RAG test

- `PLAYWRIGHT_SSO_EMAIL`
  - Email for the Microsoft SSO account

- `PLAYWRIGHT_SSO_PASSWORD`
  - Password for the Microsoft SSO account

Optional variables:

- `PLAYWRIGHT_RAG_FILE`
  - Absolute path or repo-relative path to the file used by the RAG test
  - If omitted, the test falls back to the first real file found in `fixtures/rag/`
  - If neither is present, the RAG spec skips itself

- `PLAYWRIGHT_SSO_PROVIDER_LABEL`
  - Label override for the Microsoft SSO button
  - Default: `Sign in with Microsoft`
  - Useful if the target UI customizes the provider button copy

## Env File Loading

`helpers/env.ts` loads values in this order:

1. existing shell environment
2. `.env.playwright`
3. `.env.playwright.local`

Files are parsed with a small local parser instead of pulling in a separate dotenv dependency. Existing shell variables win over file values.

## How Authentication Works

Authentication is implemented as a Playwright setup project in `setup/auth.setup.ts`.

Flow:

1. open `/auth`
2. if already authenticated, continue
3. click the Microsoft SSO button
4. optionally select an existing account tile
5. fill email if prompted
6. fill password if prompted
7. dismiss the "Stay signed in?" prompt when it appears
8. wait for `#chat-search`
9. dismiss the first-run changelog dialog if it appears
10. save storage state

Why this is written defensively:

- Microsoft login pages vary slightly across tenants
- some sessions show an account picker first
- some sessions show email and password on separate steps
- some sessions show a "Stay signed in?" confirmation and some do not

If the auth flow starts failing in the future, inspect `setup/auth.setup.ts` first.

## Why Locale Is Forced To English

The tests call `localStorage.setItem('locale', 'en-US')` before navigation.

This is important because these checks rely on stable visible text and ARIA labels such as:

- `Okay, Let's Go!`
- `Generation Info`
- `Toggle ... sources`

Without a fixed locale, assertions can become flaky across environments.

## Page Object Responsibilities

`pages/chat-page.ts` is the main UI abstraction layer.

Current responsibilities:

- navigating to the main chat page
- dismissing the changelog modal
- selecting a model by exact `data-value`
- filling and sending a prompt
- attaching a file through the hidden file input
- waiting for response completion
- waiting for citation toggle visibility
- reading the last assistant message

If future tests need to interact with chat UI, prefer extending this file instead of duplicating selectors inside specs.

## Selector Strategy

The suite intentionally prefers stable app-facing selectors already present in Open WebUI:

- `#chat-search`
- `#chat-input`
- `#send-message-button`
- `button[id^="model-selector-"][id$="-button"]`
- `#model-search-input`
- `button[data-value="<model-id>"]`
- `.chat-user`
- `.chat-assistant`
- `div[aria-label="Generation Info"]`
- `button[aria-label^="Toggle "]`

When updating selectors:

- prefer existing IDs and ARIA labels over brittle CSS chains
- prefer exact model IDs over fuzzy text matching
- keep selectors centralized in `chat-page.ts` where possible

## Completion Signals

The tests do not try to parse streaming internals.

They use these UI signals instead:

- assistant response started: `.chat-assistant`
- assistant response finished: `div[aria-label="Generation Info"]`
- RAG citations visible: `button[aria-label^="Toggle "]`

This keeps the suite aligned with actual user-visible behavior instead of implementation details.

## RAG Fixture Rules

The RAG test does not ship a real document on purpose.

Instead:

- `fixtures/rag/.gitkeep` keeps the folder in git
- the user or a future agent can place a real file there
- the RAG spec automatically uses the first non-hidden file if `PLAYWRIGHT_RAG_FILE` is unset
- if no file is available, the spec skips rather than failing

This design avoids checking in private or environment-specific fixture content while still making the suite easy to activate later.

## Typical Commands

Install dependencies:

```bash
npm install
```

Install browser binaries:

```bash
npx playwright install chromium
```

List tests with explicit env:

```bash
PLAYWRIGHT_BASE_URL=https://example.com \
PLAYWRIGHT_MODEL_IDS=model-a,model-b \
PLAYWRIGHT_RAG_MODEL_ID=model-a \
PLAYWRIGHT_SSO_EMAIL=you@example.com \
PLAYWRIGHT_SSO_PASSWORD=secret \
npm run test:e2e:playwright -- --list
```

Run the suite:

```bash
npm run test:e2e:playwright
```

Run with Playwright UI:

```bash
npm run test:e2e:playwright:ui
```

## Common Failure Modes

### `PLAYWRIGHT_BASE_URL` missing

Symptom:

- Playwright exits before listing tests

Cause:

- env not loaded or not set

Fix:

- define `PLAYWRIGHT_BASE_URL` in shell, `.env.playwright`, or `.env.playwright.local`

### Microsoft SSO button not found

Symptom:

- setup project fails on `/auth`

Cause:

- button text differs on the target instance
- SSO provider is disabled
- auth page layout changed

Fix:

- set `PLAYWRIGHT_SSO_PROVIDER_LABEL`
- inspect the target auth page
- update the candidate locators in `setup/auth.setup.ts`

### Model selection fails

Symptom:

- the spec cannot find `button[data-value="<model-id>"]`

Cause:

- the model ID is wrong
- the model is not visible to the signed-in user
- target UI changed how model options are rendered

Fix:

- confirm the exact model id in the target instance
- keep using exact id-based lookup when possible
- only fall back to label-based matching if the app removes `data-value`

### RAG test skips unexpectedly

Symptom:

- `rag-attachment.spec.ts` is skipped

Cause:

- no file exists in `fixtures/rag/`
- `PLAYWRIGHT_RAG_FILE` is unset or points to a missing file

Fix:

- place a real test file in `fixtures/rag/`
- or set `PLAYWRIGHT_RAG_FILE`

### Response never reaches `Generation Info`

Symptom:

- a model starts responding but the test times out waiting for completion

Cause:

- the target model is slow
- the backend is unhealthy
- the UI changed the completion marker

Fix:

- verify the model manually
- increase timeout only after confirming the marker is still correct
- if Open WebUI changes the completion UI, update `waitForResponseComplete()`

## How To Extend This Suite Safely

When adding new tests:

- keep target-specific values in env, not in code
- extend `chat-page.ts` instead of adding raw selectors everywhere
- prefer user-visible completion markers over internal requests
- preserve the external-client model: this repo tests Open WebUI, but does not own its source

Good future additions:

- multi-turn follow-up on the same model
- model capability checks behind optional env flags
- citation modal open/close verification
- attachment variants for PDF, markdown, or plain text

Less desirable additions:

- assumptions about internal backend APIs of the target instance
- hardcoded tenant-specific Microsoft selectors unless gated carefully
- fixtures containing private or proprietary documents

## Files Future Agents Should Check First

If something breaks, inspect these in order:

1. `playwright.config.ts`
2. `tests/playwright/helpers/env.ts`
3. `tests/playwright/setup/auth.setup.ts`
4. `tests/playwright/pages/chat-page.ts`
5. the relevant spec file

That order usually narrows whether the issue is configuration, authentication, selectors, or actual product behavior.
