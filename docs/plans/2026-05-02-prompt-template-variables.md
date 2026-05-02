# Prompt Template Variables Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add an optional, default-off generation-composer feature that treats bracket placeholders such as `[Subject]`, `[Style]`, and `[主體]` as per-generation variables, opens a variables sheet for values, sends a resolved prompt to the provider, and preserves the original template plus variable values for history/retry/provenance.

**Architecture:** Public code may include the feature, but the UI must remain hidden unless the easter-egg config switch `camelot.percival` is enabled. Keep the config codename obscure; use normal internal helper names after reading the config. Resolve variables on the frontend before creating/running generation jobs, and persist template metadata inside `GenerationJob.parameters` so existing database schema can be reused for the first slice.

**Tech Stack:** React + TypeScript frontend (`GenerationPanel.tsx`), FastAPI generation-job API, SQLite-backed GenerationJob records with JSON `parameters`, existing generation history/retry/save-as-new flows.

---

## Product decision

This is a public-code, default-off feature. It should not be advertised in README/docs/release notes until Edward decides to publicize it.

Config switch:

```json
{
  "camelot": {
    "percival": true
  }
}
```

Meaning:

- `camelot` is the hidden/easter-egg config namespace.
- `percival` enables prompt template variables / inline slots.
- Do **not** call the public config key `features`, `promptVariables`, or anything obvious.
- UI copy may still use normal wording like `Variables` once enabled.

---

## User-facing behavior

Given a generation prompt/template:

```text
A [Subject] in [Style] style
```

The composer detects two variables:

```text
Subject
Style
```

The user can open a variables sheet and enter values:

```text
Subject: cat astronaut
Style: watercolor
```

The provider receives the resolved prompt:

```text
A cat astronaut in watercolor style
```

The job metadata preserves:

```json
{
  "prompt_template": "A [Subject] in [Style] style",
  "prompt_variables": {
    "Subject": "cat astronaut",
    "Style": "watercolor"
  },
  "resolved_prompt": "A cat astronaut in watercolor style"
}
```

Supported requirements:

- English placeholders: `[Subject]`, `[Style]`, `[Camera Angle]`.
- Chinese placeholders: `[主體]`, `[風格]`, `[背景設定]`, `[鏡頭角度]`.
- Same placeholder appearing more than once is shown once in the sheet and replaced everywhere.
- Escaped literal brackets are supported from the first slice:
  - Input: `Show the text \[SALE\] beside [Subject]`
  - Variables: `Subject` only
  - Resolved: `Show the text [SALE] beside cat`
- Empty variable values block generation: clicking Generate should open the variables sheet and highlight missing fields.
- History / retry / `Use as draft` should preserve template + variable values, not collapse permanently to the resolved prompt only.
- Save as new item should default the saved prompt to the resolved prompt while keeping the generation job provenance and template metadata available.

---

## Non-goals for first slice

- No public README/docs announcement.
- No GitHub Pages demo exposure unless `camelot.percival` is deliberately enabled in that build/config.
- No schema migration unless needed; prefer `GenerationJob.parameters` JSON first.
- No advanced variable types, dropdowns, defaults, conditionals, or nested templates.
- No batch variable matrix generation yet.

---

## Proposed implementation tasks

### Task 1: Locate config delivery path and add hidden boolean helper

**Objective:** Find how frontend runtime config is loaded and expose a single helper boolean for `camelot.percival`.

**Files to inspect first:**

- `frontend/src/api/client.ts`
- `frontend/src/types.ts`
- backend config/API files that serve local config to the frontend
- any existing config drawer or settings state files

**Implementation notes:**

- Do not scatter `camelot?.percival` checks throughout the UI.
- Create or use a central helper such as:

```ts
function isInlineSlotsEnabled(config: AppConfig | undefined): boolean {
  return Boolean(config?.camelot?.percival);
}
```

- The external config key is obscure; the internal helper can be clear.

**Verification:**

- With no config key, generation composer behaves exactly as before.
- With `camelot.percival=true`, variable UI becomes eligible to appear when placeholders exist.

---

### Task 2: Add parser and resolver utility with tests

**Objective:** Add a pure TypeScript utility to extract, dedupe, escape, and resolve prompt variables.

**Suggested file:**

- Create: `frontend/src/utils/promptSlots.ts`
- Test: existing frontend test location, or create one near existing frontend unit tests if available.

**API sketch:**

```ts
export type PromptSlot = {
  name: string;
  token: string;
};

export function extractPromptSlots(template: string): PromptSlot[];
export function resolvePromptSlots(template: string, values: Record<string, string>): string;
export function unescapeLiteralBrackets(text: string): string;
```

**Parsing rules:**

- Detect `[name]` when brackets are not escaped by a preceding backslash.
- Allow Unicode names, including Chinese.
- Trim leading/trailing whitespace inside brackets for the variable name.
- Reject empty names.
- Reject names containing newlines.
- Reject very long names; cap around 40 characters after trimming.
- Deduplicate by exact trimmed name while preserving first-seen order.
- Treat `\[` and `\]` as literal brackets.

**Test cases:**

```ts
extractPromptSlots('A [Subject] in [Style] style')
// => Subject, Style

extractPromptSlots('一張[主體]的海報，風格是[風格]')
// => 主體, 風格

extractPromptSlots('[Subject] and [Subject] again')
// => Subject once

extractPromptSlots('Show \[SALE\] beside [Subject]')
// => Subject only

resolvePromptSlots('Show \[SALE\] beside [Subject]', { Subject: 'cat' })
// => 'Show [SALE] beside cat'
```

**Verification:**

- Run frontend unit tests for the new utility.
- If no existing frontend test runner exists, add a small test in the existing preferred framework or a minimal script consistent with the repo.

---

### Task 3: Add variables sheet state to `GenerationPanel.tsx`

**Objective:** When enabled and placeholders exist, show a compact variables entry point in the generation composer.

**File:**

- Modify: `frontend/src/components/GenerationPanel.tsx`

**State sketch:**

```ts
const promptSlots = useMemo(() => inlineSlotsEnabled ? extractPromptSlots(promptText) : [], [inlineSlotsEnabled, promptText]);
const [slotValues, setSlotValues] = useState<Record<string, string>>({});
const [showSlotSheet, setShowSlotSheet] = useState(false);
const [missingSlotNames, setMissingSlotNames] = useState<string[]>([]);
```

**UI behavior:**

- If `camelot.percival` is off: no button, no changed behavior.
- If on and `promptSlots.length > 0`: show a small `Variables` button/badge near the composer controls.
- Badge can show count, e.g. `Variables 2`.
- Clicking opens sheet/modal with one input per variable.
- When prompt changes and variables disappear, stale values may remain in state but should not be submitted.

**Verification:**

- Existing composer still renders normally with flag off.
- With flag on and prompt `A [Subject] in [Style] style`, Variables button appears.

---

### Task 4: Gate Generate on required variable values

**Objective:** Ensure generation cannot submit unresolved placeholders when variable mode is active.

**File:**

- Modify: `frontend/src/components/GenerationPanel.tsx`

**Create-job behavior:**

Before current `createJob` submits:

1. Extract slots from current `promptText`.
2. If enabled and slots exist, check values.
3. If any values are empty after trimming:
   - set missing list;
   - open variables sheet;
   - do not call `api.createGenerationJob`.
4. If all values exist:
   - compute `resolvedPrompt`;
   - send resolved prompt to provider/job fields;
   - include template metadata under `parameters`.

**Parameter shape:**

```json
{
  "prompt_template": "A [Subject] in [Style] style",
  "prompt_variables": {
    "Subject": "cat astronaut",
    "Style": "watercolor"
  },
  "resolved_prompt": "A cat astronaut in watercolor style"
}
```

**Important:** Preserve existing `parameters` keys:

- `requested_aspect_ratio`
- `aspect_ratio_prompt_injection`
- `quality`
- `orchestrator_model`
- `input_images`

**Verification:**

- Missing values open the sheet and do not create a job.
- Filled values create a job.
- Provider receives / job stores the resolved prompt.
- Job parameters include the original template and variable values.

---

### Task 5: Preserve template values in history / retry / Use as draft

**Objective:** Generated jobs should be reusable as templates, not just static resolved prompts.

**File:**

- Modify: `frontend/src/components/GenerationPanel.tsx`

**Behavior:**

- History preview can continue showing the resolved prompt for readability.
- `Use as draft` should prefer `parameters.prompt_template` when present, and restore `parameters.prompt_variables` into the variables state.
- Retry should keep the same template metadata and values when creating the replacement job, unless the existing retry implementation only reruns the same job. In that case, ensure rerun does not drop `parameters.prompt_template` / `prompt_variables`.

**Verification:**

- Create a template job.
- Open history.
- Use as draft.
- Confirm composer prompt returns to template form, e.g. `A [Subject] in [Style] style`.
- Confirm variables sheet is prefilled.

---

### Task 6: Save-as-new provenance behavior

**Objective:** Saved generated items should keep the user-facing prompt as resolved text while job provenance still records template details.

**File:**

- Modify: `frontend/src/components/GenerationPanel.tsx`
- Inspect backend accept-as-new endpoint if it transforms job prompt metadata.

**Behavior:**

- `buildInitialMetadata()` should continue defaulting item prompt to the resolved prompt (`job.edited_prompt_text || job.prompt_text`).
- Do not write unresolved `[Subject]` placeholders as the default saved prompt unless the user manually changes it.
- Keep `source_generation_job_id` / existing job provenance unchanged.
- Confirm job parameters retain template metadata for audit/debug.

**Verification:**

- Save a generated result as a new item.
- New item prompt defaults to resolved prompt.
- Generation job still has template + variable metadata.

---

### Task 7: Config documentation for local/internal use only

**Objective:** Document the hidden switch somewhere repo-local enough for maintainers, without adding it to public README feature lists.

**Acceptable locations:**

- This plan file is sufficient for first slice.
- Optionally add a short note to a private/local checklist if one exists.

**Do not update:**

- `README.md`
- `README_zh-TW.md`
- `README_zh-CN.md`
- public demo screenshots

unless Edward explicitly decides to publicize the feature later.

---

## Suggested test/QA checklist

Manual QA with `camelot.percival=false` or omitted:

- [ ] Composer looks and behaves exactly like current production.
- [ ] Prompt containing `[Subject]` is sent literally as before, because feature is off.

Manual QA with `camelot.percival=true`:

- [ ] Prompt `A [Subject] in [Style] style` shows Variables button with count 2.
- [ ] Generate with empty values opens variables sheet and blocks job creation.
- [ ] Filling values and generating creates a job with resolved prompt.
- [ ] Chinese placeholders like `[主體]` and `[風格]` work.
- [ ] Escaped brackets like `\[SALE\]` remain literal and are not shown as variables.
- [ ] History `Use as draft` restores template + values.
- [ ] Retry preserves template metadata.
- [ ] Save as new item defaults to resolved prompt.
- [ ] Existing generation controls, attachments, aspect ratio, quality, model selector, and history drawer continue to work.

Recommended commands before commit:

```bash
git diff --check
npm --prefix frontend test -- --run
npm --prefix frontend run build
pytest
```

If the repo has narrower/faster commands, use those first, then run the full relevant suite before merging.
