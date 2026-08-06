import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

async function importTypescript(relativePath) {
  const source = await readFile(new URL(relativePath, import.meta.url), 'utf8');
  const javascript = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(javascript).toString('base64')}`);
}

const {
  parseSearchSortQuery,
  parseStructuredSearchChips,
  removeSearchSortOperator,
} = await importTypescript('../frontend/src/utils/searchSort.ts');
const { resolveOriginalPrompt, resolvePromptText } = await importTypescript('../frontend/src/utils/prompts.ts');
const { downloadFileName, imageDisplayPath, imageThumbnailPath, selectPrimaryImage } = await importTypescript('../frontend/src/utils/images.ts');
const { generationFailure } = await importTypescript('../frontend/src/utils/generationFailures.ts');
const { generationSetProgressText, providerPauseSeconds } = await importTypescript('../frontend/src/utils/generationSets.ts');
const { APPEARANCE_STORAGE_KEY, DEFAULT_APPEARANCE, normalizeAppearance } = await importTypescript('../frontend/src/utils/appearance.ts');
const {
  createGenerationReviewSession,
  generationReviewNext,
  generationResultPosition,
  generationReviewSummary,
  generationReviewSlotNavigation,
  generationRetryGroupFields,
  generationSiblingNavigation,
  mapGenerationRetryJobs,
  mapGenerationRetryToReviewSlot,
  reconcileGenerationReviewSession,
  resolveGenerationReviewSlot,
  resolveGenerationRetryGroup,
  retainPendingRetryJobIds,
} = await importTypescript('../frontend/src/utils/generationSiblings.ts');
const { makeTranslator } = await importTypescript('../frontend/src/utils/i18n.ts');

test('search helpers parse sort operators and supported filter chips', () => {
  assert.deepEqual(parseSearchSortQuery('  cats sort:title  tag:poster '), {
    q: 'cats tag:poster',
    sort: 'title_asc',
    explicitSort: true,
  });
  assert.equal(removeSearchSortOperator('cats sort:oldest source:demo'), 'cats source:demo');
  assert.deepEqual(
    parseStructuredSearchChips('created:7d tag:poster favorite:true has:image created:forever'),
    ['created:7d', 'tag:poster', 'favorite:true', 'has:image'],
  );
});

test('prompt helpers prefer requested text and fall back predictably', () => {
  const prompts = [
    { language: 'zh_hant', text: '原始提示', is_original: true },
    { language: 'en', text: 'English prompt', is_original: false },
  ];

  assert.equal(resolveOriginalPrompt(prompts)?.text, '原始提示');
  assert.equal(resolvePromptText(prompts, 'en'), 'English prompt');
  assert.equal(resolvePromptText(prompts, 'zh_hans'), 'English prompt');
  assert.equal(resolvePromptText([], 'origin', 'Fallback title'), 'Fallback title');
});

test('image helpers select result images and produce safe download names', () => {
  const reference = { role: 'reference_image', original_path: 'reference.png' };
  const result = { role: 'result_image', preview_path: 'preview.webp', original_path: 'result.png' };

  assert.equal(selectPrimaryImage([reference, result]), result);
  assert.equal(imageDisplayPath(result), 'preview.webp');
  assert.equal(imageThumbnailPath({ ...result, thumb_path: 'thumb.webp' }), 'thumb.webp');
  assert.equal(imageThumbnailPath({ ...result, thumb_path: undefined }), 'preview.webp');
  assert.equal(downloadFileName('  Poster / Study  ', 'preview.webp?size=large'), 'poster-study.webp');
});

test('batch review slots retain accepted target metadata and result image paths', () => {
  const job = {
    id: 'target-job', generation_group_id: 'target-batch', generation_group_index: 1, generation_group_size: 2,
    status: 'succeeded', result_path: 'generation-results/target-job/result.png',
    created_at: '2026-07-25T00:01:00Z', updated_at: '2026-07-25T00:01:00Z',
  };
  const sibling = { ...job, id: 'target-sibling', generation_group_index: 2, result_path: null, status: 'queued' };
  const session = createGenerationReviewSession([job, sibling], job);
  const resolved = resolveGenerationReviewSlot(session, { ...job, status: 'accepted', result_path: null }, 'saved', {
    targetItemId: 'item-target', targetItemTitle: 'Saved target', resultPath: job.result_path,
  });
  const slot = resolved.slots[0];
  assert.equal(slot.targetItemId, 'item-target');
  assert.equal(slot.targetItemTitle, 'Saved target');
  assert.equal(slot.resultPath, job.result_path);
  assert.equal(generationReviewSlotNavigation(resolved, 'target-job').next?.index, 2);

  const discarded = resolveGenerationReviewSlot(resolved, { ...job, status: 'discarded', result_path: null }, 'discarded');
  assert.equal(discarded.slots[0].resultPath, undefined, 'discarded slots must not retain deleted result paths');
});

test('review reconciliation clears deleted result paths for terminal jobs', () => {
  const job = {
    id: 'deleted-result', generation_group_id: 'deleted-batch', generation_group_index: 1, generation_group_size: 2,
    status: 'discarded', result_path: null,
    created_at: '2026-07-25T00:01:00Z', updated_at: '2026-07-25T00:01:00Z',
  };
  const sibling = { ...job, id: 'deleted-sibling', generation_group_index: 2, status: 'queued' };
  const session = createGenerationReviewSession([job, sibling], job);
  const withStalePath = { ...session, slots: session.slots.map(slot => slot.index === 1 ? { ...slot, resultPath: 'generation-results/deleted-result/result.png' } : slot) };
  const reconciled = reconcileGenerationReviewSession(withStalePath, [job, sibling]);
  assert.equal(reconciled.slots[0].resultPath, undefined);
  const failed = resolveGenerationReviewSlot(withStalePath, { ...job, status: 'failed' }, 'failed');
  assert.equal(failed.slots[0].resultPath, undefined);
});

test('pending retry ids clear after a loaded retry reaches a terminal state', () => {
  const base = { generation_group_id: 'retry-state', created_at: '2026-07-25T00:01:00Z', updated_at: '2026-07-25T00:01:00Z' };
  const jobs = [
    { ...base, id: 'queued-retry', status: 'queued' },
    { ...base, id: 'done-retry', status: 'succeeded' },
  ];
  assert.deepEqual(retainPendingRetryJobIds(['queued-retry', 'done-retry', 'not-loaded'], jobs), ['queued-retry', 'not-loaded']);
});

test('retry metadata preserves an absent-original batch only when identity and slot are explicit', () => {
  const base = { created_at: '2026-07-25T00:01:00Z', updated_at: '2026-07-25T00:01:00Z' };
  const retry = {
    ...base,
    id: 'metadata-retry',
    status: 'queued',
    metadata: {
      retry_of_generation_job_id: 'missing-original',
      generation_group_id: 'metadata-batch',
      generation_group_index: 2,
      generation_group_size: 3,
    },
  };
  const mapped = mapGenerationRetryJobs([retry])[0];
  assert.equal(generationRetryGroupFields(retry)?.generation_group_id, 'metadata-batch');
  assert.equal(mapped.generation_group_id, 'metadata-batch');
  assert.equal(mapped.generation_group_index, 2);
  assert.equal(mapped.generation_group_size, 3);

  const original = { ...base, id: 'chain-original', status: 'failed', generation_group_id: 'chain-batch', generation_group_index: 1, generation_group_size: 3 };
  const retryOne = { ...base, id: 'chain-retry-one', status: 'failed', metadata: { retry_of_generation_job_id: original.id } };
  const retryTwo = { ...base, id: 'chain-retry-two', status: 'queued', metadata: { retry_of_generation_job_id: retryOne.id } };
  const resolution = resolveGenerationRetryGroup(retryTwo, [retryTwo, retryOne, original]);
  assert.deepEqual(resolution?.ancestorIds, [retryOne.id, original.id]);
  assert.equal(resolution?.sourceJob?.id, original.id);
  assert.equal(mapGenerationRetryJobs([retryTwo, retryOne, original])[0].generation_group_id, original.generation_group_id);

  const unknown = { ...base, id: 'unknown-retry', status: 'queued', metadata: { retry_of_generation_job_id: 'missing-original' } };
  assert.equal(mapGenerationRetryJobs([unknown])[0].generation_group_id, undefined);

  const cycleA = { ...base, id: 'cycle-a', status: 'queued', metadata: { retry_of_generation_job_id: 'cycle-b', generation_group_id: 'cycle-batch', generation_group_index: 1, generation_group_size: 2 } };
  const cycleB = { ...base, id: 'cycle-b', status: 'queued', metadata: { retry_of_generation_job_id: 'cycle-a' } };
  assert.equal(resolveGenerationRetryGroup(cycleA, [cycleA, cycleB]), undefined);
});

test('generation failure guidance follows classified metadata exactly', () => {
  const cases = [
    ['policy_violation', 'Cannot generate this image', 'The provider refused this request because it may violate policy. Try changing the prompt.'],
    ['rate_limited', 'Generation is temporarily rate limited', 'Please wait a bit before trying again.'],
    ['provider_unavailable', 'Provider is temporarily unavailable', 'The provider is temporarily unavailable. Please try again shortly.'],
    ['auth_required', 'Provider connection needs attention', 'Reconnect in Config → Providers before retrying.'],
    ['unknown', 'Generation failed', 'You can retry the job or adjust the prompt.'],
  ];

  for (const [kind, title, guidance] of cases) {
    assert.deepEqual(generationFailure({ metadata: { error_kind: kind } }), { kind, title, guidance });
  }
});

test('generation failure guidance never reclassifies diagnostic text', () => {
  assert.equal(generationFailure({
    metadata: { error_kind: 'provider_unavailable' },
    error: 'Token refresh is temporarily unavailable',
  }).kind, 'provider_unavailable');
  assert.equal(generationFailure({ metadata: { error_kind: 'not-a-kind' }, error: '429 rate limit' }).kind, 'unknown');
  assert.equal(generationFailure({ error: 'authentication required' }).kind, 'unknown');
});

test('generation set progress reports exact terminal and active counts', () => {
  assert.equal(generationSetProgressText({
    completed: 2,
    total: 5,
    running: 1,
    queued: 2,
    succeeded: 1,
    failed: 1,
    cancelled: 0,
  }), '2 of 5 finished · 1 running · 2 queued · 1 ready · 1 failed');
});

test('provider pause countdown derives from the authoritative deadline', () => {
  const currentTime = Date.parse('2026-07-19T00:00:00Z');
  assert.equal(providerPauseSeconds({ paused: true, paused_until: '2026-07-19T00:01:05Z', retry_after_seconds: 65 }, currentTime), 65);
  assert.equal(providerPauseSeconds({ paused: true, paused_until: 'invalid', retry_after_seconds: 60 }, currentTime), 60);
  assert.equal(providerPauseSeconds({ paused: true, paused_until: '2026-07-18T23:59:59Z', retry_after_seconds: 60 }, currentTime), 0);
  assert.equal(providerPauseSeconds({ paused: false, paused_until: '2026-07-19T00:01:05Z', retry_after_seconds: 65 }, currentTime), 0);
});

test('appearance presets stay browser-local and reject unknown values', () => {
  assert.equal(APPEARANCE_STORAGE_KEY, 'image-prompt-library.appearance.v1');
  assert.equal(DEFAULT_APPEARANCE, 'gallery_vermilion');
  assert.equal(normalizeAppearance('gallery_vermilion'), 'gallery_vermilion');
  assert.equal(normalizeAppearance('pine_archive'), 'pine_archive');
  assert.equal(normalizeAppearance('aubergine_ink'), 'aubergine_ink');
  assert.equal(normalizeAppearance('dark'), 'gallery_vermilion');
  assert.equal(normalizeAppearance(null), 'gallery_vermilion');
});

test('appearance names are localized without changing preset identifiers', () => {
  const traditional = makeTranslator('zh_hant');
  const simplified = makeTranslator('zh_hans');
  const english = makeTranslator('en');

  assert.deepEqual(
    ['appearanceGalleryVermilion', 'appearancePineArchive', 'appearanceAubergineInk'].map(key => traditional(key)),
    ['朱紅', '松綠', '茄紫'],
  );
  assert.deepEqual(
    ['appearanceGalleryVermilion', 'appearancePineArchive', 'appearanceAubergineInk'].map(key => simplified(key)),
    ['朱红', '松绿', '茄紫'],
  );
  assert.deepEqual(
    ['appearanceGalleryVermilion', 'appearancePineArchive', 'appearanceAubergineInk'].map(key => english(key)),
    ['Red', 'Green', 'Purple'],
  );
});

test('generation sibling navigation sorts a batch and does not wrap', () => {
  const jobs = [1, 3, 2].map(index => ({
    id: `job-${index}`,
    generation_group_id: 'batch-1',
    generation_group_index: index,
    generation_group_size: 3,
    status: 'succeeded',
    created_at: `2026-07-25T00:0${index}:00Z`,
    updated_at: `2026-07-25T00:0${index}:00Z`,
  }));
  const first = generationSiblingNavigation(jobs, jobs[0]);
  assert.deepEqual(first.siblings.map(job => job.id), ['job-1', 'job-2', 'job-3']);
  assert.equal(first.index, 0);
  assert.equal(first.previous, undefined);
  assert.equal(first.next?.id, 'job-2');
  const last = generationSiblingNavigation(jobs, jobs[1]);
  assert.equal(last.index, 2);
  assert.equal(last.next, undefined);
  assert.equal(generationSiblingNavigation(jobs, { ...jobs[0], generation_group_id: null }).total, 1);
});

test('generation review advances forward, wraps, and skips resolved jobs', () => {
  const jobs = [1, 2, 3].map(index => ({
    id: `review-${index}`,
    generation_group_id: 'review-batch',
    generation_group_index: index,
    generation_group_size: 3,
    status: index === 1 ? 'accepted' : 'succeeded',
    accepted_image_id: index === 1 ? `image-${index}` : null,
    result_path: `generation-results/review-${index}/result.png`,
    created_at: `2026-07-25T00:0${index}:00Z`,
    updated_at: `2026-07-25T00:0${index}:00Z`,
  }));
  const session = createGenerationReviewSession(jobs, jobs[1]);
  assert.equal(session.generationGroupSize, 3);
  assert.equal(generationReviewNext(jobs, session, jobs[1].id)?.id, jobs[2].id);
  assert.equal(generationReviewNext(jobs, session, jobs[2].id)?.id, jobs[1].id, 'wraps to the next actionable slot');
});

test('generation review resumes when a later batch result becomes ready', () => {
  const completed = {
    id: 'later-1', generation_group_id: 'later-batch', generation_group_index: 1, generation_group_size: 2,
    status: 'succeeded', result_path: 'generation-results/later-1/result.png', created_at: '2026-07-25T00:01:00Z', updated_at: '2026-07-25T00:01:00Z',
  };
  const waiting = {
    ...completed,
    id: 'later-2', generation_group_index: 2, status: 'queued', result_path: null,
    created_at: '2026-07-25T00:02:00Z', updated_at: '2026-07-25T00:02:00Z',
  };
  const session = resolveGenerationReviewSlot(createGenerationReviewSession([completed, waiting], completed), completed, 'saved');
  assert.equal(generationReviewNext([completed, waiting], session, completed.id), undefined);
  const ready = { ...waiting, status: 'succeeded', result_path: 'generation-results/later-2/result.png' };
  assert.equal(generationReviewNext([completed, ready], session, completed.id)?.id, ready.id);
});

test('generation review keeps stable positions when a retry replaces a slot', () => {
  const original = {
    id: 'retry-original', generation_group_id: 'retry-batch', generation_group_index: 2, generation_group_size: 4,
    status: 'failed', result_path: null, created_at: '2026-07-25T00:02:00Z', updated_at: '2026-07-25T00:02:00Z',
  };
  const sibling = { ...original, id: 'retry-sibling', generation_group_index: 1, status: 'succeeded', result_path: 'generation-results/retry-sibling/result.png' };
  const retry = { ...original, id: 'retry-replacement', status: 'queued' };
  const session = createGenerationReviewSession([original, sibling], original);
  const mapped = mapGenerationRetryToReviewSlot(session, original, retry);
  assert.deepEqual(generationResultPosition({ ...retry, generation_group_id: mapped.generationGroupId, generation_group_index: 2, generation_group_size: 4 }), { index: 2, total: 4 });
  assert.equal(mapped.slots.find(slot => slot.index === 2)?.currentJobId, retry.id);
  assert.equal(generationReviewSummary([sibling, retry], mapped, [retry.id]).pendingRetry, 1);
});

test('generation review waits for missing paginated slots and reconciles them later', () => {
  const first = {
    id: 'paged-1', generation_group_id: 'paged-batch', generation_group_index: 1, generation_group_size: 3,
    status: 'succeeded', result_path: 'generation-results/paged-1/result.png', created_at: '2026-07-25T00:01:00Z', updated_at: '2026-07-25T00:01:00Z',
  };
  const later = [2, 3].map(index => ({
    ...first,
    id: `paged-${index}`,
    generation_group_index: index,
    result_path: `generation-results/paged-${index}/result.png`,
    created_at: `2026-07-25T00:0${index}:00Z`,
    updated_at: `2026-07-25T00:0${index}:00Z`,
  }));
  const initial = createGenerationReviewSession([first], first);
  assert.equal(generationReviewSummary([first], initial).pendingGeneration, 2);
  assert.equal(generationReviewSummary([first], initial).complete, false);

  const reconciled = reconcileGenerationReviewSession(initial, [first, ...later]);
  assert.deepEqual(reconciled.slots.map(slot => slot.currentJobId), ['paged-1', 'paged-2', 'paged-3']);
  assert.equal(generationReviewNext([first, ...later], reconciled, first.id)?.id, 'paged-2');
});

test('generation sibling navigation deduplicates a retry replacement at its stable slot', () => {
  const jobs = [1, 2, 3].map(index => ({
    id: `dedupe-${index}`,
    generation_group_id: 'dedupe-batch',
    generation_group_index: index,
    generation_group_size: 3,
    status: index === 2 ? 'failed' : 'succeeded',
    result_path: index === 2 ? null : `generation-results/dedupe-${index}/result.png`,
    created_at: `2026-07-25T00:0${index}:00Z`,
    updated_at: `2026-07-25T00:0${index}:00Z`,
  }));
  const replacement = {
    ...jobs[1],
    id: 'dedupe-2-retry',
    status: 'succeeded',
    result_path: 'generation-results/dedupe-2-retry/result.png',
    created_at: '2026-07-25T00:12:00Z',
    updated_at: '2026-07-25T00:12:00Z',
  };
  const navigation = generationSiblingNavigation([...jobs, replacement], replacement);
  assert.equal(navigation.total, 3);
  assert.deepEqual(navigation.siblings.map(job => job.id), ['dedupe-1', 'dedupe-2-retry', 'dedupe-3']);
  assert.equal(navigation.index, 1);
});

test('generation review records terminal actions and reports a complete batch summary', () => {
  const jobs = [1, 2, 3, 4, 5].map(index => ({
    id: `summary-${index}`,
    generation_group_id: 'summary-batch',
    generation_group_index: index,
    generation_group_size: 5,
    status: index === 5 ? 'cancelled' : 'succeeded',
    result_path: index === 5 ? null : `generation-results/summary-${index}/result.png`,
    created_at: `2026-07-25T00:0${index}:00Z`,
    updated_at: `2026-07-25T00:0${index}:00Z`,
  }));
  let session = createGenerationReviewSession(jobs, jobs[0]);
  session = resolveGenerationReviewSlot(session, jobs[0], 'saved');
  session = resolveGenerationReviewSlot(session, jobs[1], 'attached');
  session = resolveGenerationReviewSlot(session, jobs[2], 'discarded');
  session = resolveGenerationReviewSlot(session, jobs[3], 'saved');

  assert.equal(generationReviewNext(jobs, session, jobs[3].id), undefined);
  assert.deepEqual(generationReviewSummary(jobs, session), {
    total: 5,
    actionable: 0,
    pendingGeneration: 0,
    pendingRetry: 0,
    saved: 2,
    attached: 1,
    discarded: 1,
    failedOrCancelled: 1,
    resolved: 5,
    complete: true,
  });
  assert.deepEqual(session.slots.map(slot => slot.index), [1, 2, 3, 4, 5], 'original batch numbering remains stable');
});

test('frontend shell declares a mobile viewport and root mount point', async () => {
  const html = await readFile(new URL('../frontend/index.html', import.meta.url), 'utf8');

  assert.match(html, /name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/);
  assert.match(html, /<div id="root"><\/div>/);
});
