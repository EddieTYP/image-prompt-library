import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

// Execute the actual component handlers, without duplicating their logic.
const generation = await readFile(new URL('../frontend/src/components/GenerationPanel.tsx', import.meta.url), 'utf8');
const app = await readFile(new URL('../frontend/src/App.tsx', import.meta.url), 'utf8');
const detail = await readFile(new URL('../frontend/src/components/ItemDetailModal.tsx', import.meta.url), 'utf8');
const editor = await readFile(new URL('../frontend/src/components/ItemEditorModal.tsx', import.meta.url), 'utf8');
const modalFocus = await readFile(new URL('../frontend/src/hooks/useModalFocus.ts', import.meta.url), 'utf8');
function handler(source, name, context) {
  const tree = ts.createSourceFile('component.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let expression;
  function visit(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(tree) === name) expression = node.initializer;
    if (ts.isFunctionDeclaration(node) && node.name?.getText(tree) === name) expression = node;
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(expression, `Missing handler ${name}`);
  const code = ts.transpileModule(`(${expression.getText(tree).replace(/^export\s+/, '')})`, { compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React } }).outputText;
  return vm.runInNewContext(code, context);
}
function draftContext(overrides = {}) {
  const context = {
    busy: false, isClosing: false, isHistoryReview: false,
    promptText: 'draft', editAttachments: [{ id: 'ref' }], templateValues: {},
    openingDraftRef: { current: { prompt: 'draft', attachmentIds: 'ref', templateValues: {} } },
    t: value => value, confirms: 0, allowDiscard: false,
    setIsClosing: value => { context.isClosing = value; },
    window: { confirm: () => { context.confirms++; return context.allowDiscard; } },
    ...overrides,
  };
  context.hasUnsubmittedDraft = handler(generation, 'hasUnsubmittedDraft', context);
  return context;
}

test('history review cannot bypass dirty prompt, attachment or template cancellation', () => {
  for (const change of [{ promptText: 'edited' }, { editAttachments: [] }, { templateValues: { subject: 'cat' } }]) {
    const c = draftContext({ ...change, isHistoryReview: true });
    const close = handler(generation, 'handleClose', c);
    assert.equal(close(), false);
    assert.equal(c.confirms, 1);
    assert.equal(c.isClosing, false);
    c.allowDiscard = true;
    assert.equal(close(), true);
    assert.equal(c.isClosing, true);
  }
  const clean = draftContext({ isHistoryReview: true });
  assert.equal(handler(generation, 'handleClose', clean)(), true);
  assert.equal(clean.confirms, 0);
});

test('view saved target does not navigate after cancelled draft discard', () => {
  for (const allowed of [false, true]) {
    const pendingAcceptedRef = { current: undefined };
    const calls = [];
    const open = handler(generation, 'openReviewTarget', {
      pendingAcceptedRef, t: value => value,
      handleClose: (...args) => { calls.push(args); return allowed; },
    });
    open('saved-item', 'Saved');
    assert.deepEqual(calls, [[]]);
    assert.equal(pendingAcceptedRef.current?.item.id, allowed ? 'saved-item' : undefined);
  }
});

test('submitted template values are clean but later edits and cleared values remain dirty', () => {
  const c = draftContext({ templateValues: { subject: 'cup' } });
  c.openingDraftRef.current.templateValues = { subject: 'cup' };
  assert.equal(c.hasUnsubmittedDraft(), false);
  c.templateValues = { subject: 'cat' };
  assert.equal(c.hasUnsubmittedDraft(), true);
  c.templateValues = {};
  assert.equal(c.hasUnsubmittedDraft(), true);
});

test('replacing an unsent draft can be cancelled before any state changes', () => {
  const c = draftContext({ promptText: 'new unsent prompt' });
  handler(generation, 'useJobAsDraft', c)({ id: 'old-job' });
  assert.equal(c.confirms, 1);
  assert.equal(c.promptText, 'new unsent prompt');
});

test('generation acknowledgement rebaselines the submitted snapshot, not edits typed while waiting', async () => {
  let resolve;
  const c = draftContext({ promptText: 'submitted A', templateValues: { subject: 'cup' } });
  Object.assign(c, {
    createJobInFlightRef: { current: false }, hasMissingTemplateValues: false,
    resolvedPrompt: 'submitted A', selectedProviderCanGenerateDraft: true,
    provider: 'openai_codex_oauth_native', batchReviewSession: undefined, batchReviewPaused: false,
    jobsRequestRef: { current: 0 }, defaultPrompt: '', defaultPromptLanguage: 'en', item: undefined,
    hasTemplateVariables: false, selectedProvider: undefined, aspectRatio: 'auto', quality: 'high',
    imageAttachmentPayload: () => [], setBusy: () => {}, setMessage: value => { c.message = value; },
    setGenerationCountMenuOpen: () => {}, setHistoryReviewJobId: () => {}, invalidateGenerationSetRequest: () => {},
    setActiveGenerationSetSafely: () => {}, invalidateGenerationRefreshRequests: () => {}, updateGenerationJobs: () => {},
    setBatchReviewSession: () => {}, setBatchReviewPaused: () => {}, setPendingRetryJobIds: () => {}, setActiveJobId: () => {},
    onQueueChangedRef: { current: undefined }, api: { createGenerationJob: () => new Promise(done => { resolve = done; }) },
    window: { requestAnimationFrame: () => {} },
  });
  const pending = handler(generation, 'createJob', c)();
  c.promptText = 'new B';
  c.templateValues = { subject: 'cat' };
  resolve({ id: 'created', status: 'queued' });
  await pending;
  assert.equal(c.openingDraftRef.current.prompt, 'submitted A');
  assert.equal(c.openingDraftRef.current.templateValues.subject, 'cup');
  assert.equal(c.hasUnsubmittedDraft(), true);
  assert.equal(c.message, '');
  c.promptText = 'submitted A'; c.templateValues = { subject: 'cup' };
  assert.equal(c.hasUnsubmittedDraft(), false);
});

test('editor locks native fields while saving and keeps a focus destination', () => {
  assert.match(editor, /<fieldset className="editor-grid" disabled=\{saving \|\| deleting\}>/);
  assert.match(editor, /if \(saving \|\| deleting\) editorDialogRef\.current\?\.focus/);
});

test('both retry paths preserve edits made while the request is pending', async () => {
  for (const name of ['discardAndRetryJob', 'retryFailedJob']) {
    let resolve;
    const c = draftContext({ promptText: 'unsent B' });
    const pendingApi = () => new Promise(done => { resolve = done; });
    const overwrite = () => { throw new Error('Retry must not replace the composer'); };
    Object.assign(c, {
      allowDiscard: true, canRetryFailedJob: () => true, ensureBatchReviewSession: () => undefined,
      setBusy: () => {}, setActiveJobId: () => {}, setMessage: () => {},
      invalidateGenerationRefreshRequests: () => {}, updateGenerationJobs: update => update([]),
      setFocusedJobHighlightId: () => {}, onQueueChangedRef: {}, setHistoryReviewJobId: () => {},
      setPromptText: overwrite, setEditAttachments: overwrite, setAspectRatio: overwrite, setTemplateValues: overwrite,
      setQuality: overwrite, setProvider: overwrite,
      refreshJobs: () => { throw new Error('Unexpected retry failure'); },
      api: { discardAndRetryGenerationJob: pendingApi, retryGenerationJob: pendingApi },
    });
    const pending = handler(generation, name, c)({ id: 'old-A' });
    c.promptText = 'newer C'; c.templateValues = { subject: 'latest' };
    resolve(name === 'discardAndRetryJob' ? { retry_job: { id: 'retry' }, discarded_job: { id: 'old-A' } } : { id: 'retry' });
    await pending;
    assert.equal(c.promptText, 'newer C');
    assert.equal(c.templateValues.subject, 'latest');
    assert.equal(c.editAttachments[0].id, 'ref');
  }
});

test('history results expose prompt and position rather than identical configuration-only names', () => {
  assert.match(generation, /visibleJobs\.map\(\(job, index\)/);
  assert.match(generation, /aria-label=\{`\$\{t\('result'\)\} \$\{index \+ 1\}: \$\{jobPrompt\(job\)\.slice\(0, 100\)\}/);
});

test('history focus restores only after the closed drawer has committed', () => {
  const tree = ts.createSourceFile('component.tsx', generation, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let effect;
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(tree) === 'useEffect'
      && node.arguments[0]?.getText(tree).includes('if (showHistoryDrawer || !historyFocusReturnPendingRef.current)')) effect = node.arguments[0];
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(effect);
  const code = ts.transpileModule(`(${effect.getText(tree)})`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  for (const showHistoryDrawer of [true, false]) {
    for (const pending of [true, false]) {
      let focused = 0;
      const context = { showHistoryDrawer, historyFocusReturnPendingRef: { current: pending }, historyTriggerRef: { current: null },
        generationDialogRef: { current: { querySelector: () => ({ focus: () => { focused++; } }) } } };
      vm.runInNewContext(code, context)();
      assert.equal(focused, !showHistoryDrawer && pending ? 1 : 0);
      if (focused) assert.equal(context.historyFocusReturnPendingRef.current, false);
    }
  }
});

test('accepting a result never closes the composer, and records only that job target', () => {
  for (const isHistoryReview of [true, false]) {
    const pendingAcceptedRef = { current: undefined };
    const notifications = [];
    const closes = [];
    let targets = {};
    const save = handler(generation, 'queueAccepted', {
      isHistoryReview, pendingAcceptedRef,
      onAcceptedRef: { current: (...args) => notifications.push(args) },
      handleClose: (...args) => closes.push(args),
      setAcceptedTargets: update => { targets = update(targets); },
    });
    save({ id: 'saved', title: 'Saved item' }, 'saved message', 'job-A');
    assert.equal(closes.length, 0);
    assert.equal(pendingAcceptedRef.current, undefined);
    assert.deepEqual(notifications, [[undefined, 'saved message']]);
    assert.equal(targets['job-A'].id, 'saved');
    assert.equal(targets['job-B'], undefined);
  }
});

test('discard and regenerate runs directly without confirmation and still respects busy state', async () => {
  const calls = [];
  const context = {
    busy: false, t: value => value,
    window: { confirm: () => { throw new Error('Must not prompt'); } },
    ensureBatchReviewSession: () => { calls.push('review'); },
    api: { discardAndRetryGenerationJob: async () => { calls.push('api'); return { retry_job: { id: 'retry' }, discarded_job: { id: 'result' } }; } },
    setBusy: value => { calls.push(`busy:${value}`); },
    setActiveJobId: () => {}, setMessage: () => {},
    invalidateGenerationRefreshRequests: () => {}, updateGenerationJobs: update => update([]),
    setFocusedJobHighlightId: () => {}, onQueueChangedRef: {}, setHistoryReviewJobId: () => {},
    refreshJobs: () => { throw new Error('Unexpected failure'); },
  };
  await handler(generation, 'discardAndRetryJob', context)({ id: 'result' });
  assert.deepEqual(calls, ['review', 'busy:true', 'api', 'busy:false']);
  context.busy = true;
  await handler(generation, 'discardAndRetryJob', context)({ id: 'result' });
  assert.deepEqual(calls, ['review', 'busy:true', 'api', 'busy:false']);
});

test('generation details suppress duplicated prompts but retain distinct historical text', async () => {
  const item = { prompts: [{ text: 'Original text' }, { text: '翻譯' }] };
  for (const [text, expected] of [[undefined, false], ['', false], ['  ', false], [' Original text\n', false], ['翻譯', false], ['Earlier prompt', true]]) {
    assert.equal(handler(detail, 'hasDistinctGenerationPrompt', { item, selectedImage: { generation_prompt_text: text } }), expected);
  }
  assert.match(detail, /selectedImage\?\.generation_job_id && canGenerate && <button[^>]*generation-history-link/);
  assert.match(detail, /className="prompt-generate-action"[^\n]*aria-label=\{t\('reusePrompt'\)\} title=\{t\('reusePrompt'\)\}>\{imageGenerateIcon\}<\/button>/);
  assert.doesNotMatch(detail, /prompt-panel-footer|mobile-generate-variant-label/);
  assert.doesNotMatch(detail, /prompt-copy-(?:label|full-label|short-label)/);
  assert.match(detail, /<span className="prompt-block-actions">[\s\S]*?className="prompt-copy-icon"[\s\S]*?className="prompt-edit-icon"[\s\S]*?className="prompt-generate-action"[\s\S]*?<\/span>/);
  assert.doesNotMatch(detail, /<strong>\{t\('cardPrompt'\)\}<\/strong>/);
  const styles = await readFile(new URL('../frontend/src/styles.css', import.meta.url), 'utf8');
  assert.match(styles, /\.detail-side \.prompt-panel-body\{max-height:min\(50dvh,480px\);overflow-y:auto/);
  assert.match(styles, /\.detail-side \.prompt-language-tabs\.tabs\{display:flex;flex:0 0 auto/);
  assert.match(styles, /@media\(max-width:360px\)\{\.detail-side \.prompt-language-tabs\.tabs\{gap:0\}\.detail-side \.prompt-language-tabs\.tabs button\{flex-basis:36px;width:36px;min-width:36px\}\}/);
});

test('detail toolbar keeps distinct generation silhouettes and accessible single-line language tabs', () => {
  assert.match(detail, /const imageEditIcon = <svg width="20" height="20"[^\n]*strokeWidth="1.75"/);
  assert.match(detail, /const imageGenerateIcon = <WandSparkles size=\{20\} strokeWidth=\{1.75\} aria-hidden="true"/);
  assert.doesNotMatch(detail, /className="prompt-origin-label"/);
  assert.match(detail, /aria-label=\{`\$\{LANG_LABELS\[promptLanguage\][^\n]*t\('origin'\)/);
  assert.match(detail, /title=\{isOriginalPrompt \? t\('origin'\)/);
  assert.match(detail, /className="detail-identity"/);
});

test('mobile toast clears the fixed command dock and respects the safe area', async () => {
  const styles = await readFile(new URL('../frontend/src/styles.css', import.meta.url), 'utf8');
  assert.match(styles, /\.toast\{bottom:calc\(84px \+ env\(safe-area-inset-bottom\)\);max-width:calc\(100vw - 24px\)\}/);
});

test('composer keeps a visible prompt label after typing', () => {
  assert.match(generation, /<label className="generation-prompt-label" htmlFor="generation-prompt-input">/);
  assert.match(generation, /<textarea id="generation-prompt-input"[^\n]*aria-label=\{t\('generationPrompt'\)\}/);
});

test('provider readiness stays loading until the request settles and ignores an unmounted response', async () => {
  const tree = ts.createSourceFile('component.tsx', generation, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let effect;
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(tree) === 'useEffect'
      && node.getText(tree).includes('api.generationProviders()')) effect = node;
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(effect);
  const code = ts.transpileModule(effect.getText(tree), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  for (const outcome of ['success', 'failure', 'unmounted']) {
    let resolve, reject, cleanup;
    const request = new Promise((yes, no) => { resolve = yes; reject = no; });
    const loading = [], providers = [];
    vm.runInNewContext(code, {
      useEffect: callback => { cleanup = callback(); }, api: { generationProviders: () => request },
      setProvidersLoading: value => loading.push(value), setProviders: value => providers.push(value),
      setProvider: () => {}, providerCanGenerate: () => true, defaultAiProvider: 'openai_codex_oauth_native',
      item: undefined, initialJobId: undefined, refreshStatus: () => {},
      jobsRequestRef: { current: 0 }, statusRefreshRequestRef: { current: 0 }, statusRefreshBusyRef: { current: false },
    });
    assert.deepEqual(loading, [true]);
    if (outcome === 'unmounted') cleanup();
    if (outcome === 'failure') reject(new Error('unavailable'));
    else resolve([{ provider: 'openai_codex_oauth_native' }]);
    await new Promise(done => setImmediate(done));
    assert.deepEqual(loading, outcome === 'unmounted' ? [true] : [true, false]);
    assert.equal(providers.length, outcome === 'unmounted' ? 0 : 1);
  }
  assert.match(generation, /const selectedProviderCanGenerate = !providersLoading && providerCanGenerate\(selectedProvider\)/);
  assert.match(generation, /!providersLoading && !selectedProviderCanGenerateDraft && <div className="generation-provider-status"/);
});

test('pending generated-image save announces saving instead of an inert save action', () => {
  assert.match(generation, /aria-label=\{t\('saveGeneratedImageAsNew'\)\}\s+aria-busy=\{busy\}/);
  const expression = generation.match(/onClick=\{acceptAsNew\} disabled=\{busy\}>\{([^\n]+)\}<\/button>/)?.[1];
  assert.ok(expression);
  for (const [busy, hasNext, expected] of [[true, true, 'saving'], [true, false, 'saving'], [false, true, 'saveAndContinue'], [false, false, 'confirmSave']]) {
    assert.equal(vm.runInNewContext(expression, { busy, batchReviewSession: {}, generationReviewNext: () => hasNext, jobs: [], reviewJob: { id: 'job' }, t: key => key }), expected);
  }
});

test('detail generation cannot leave an unconfirmed prompt edit or pending save', () => {
  const calls = [];
  const context = { item: { id: 'item' }, copyText: 'saved prompt', prompt: { text: 'saved prompt', language: 'en' }, selectedImage: { id: 'image' }, onGenerate: (...args) => calls.push(args), editingPromptLanguage: 'en', inlineMutationBusy: false };
  const generate = handler(detail, 'generateFromSelection', context);
  generate(false); generate(true);
  assert.equal(calls.length, 0);
  context.editingPromptLanguage = undefined; context.inlineMutationBusy = true;
  generate(false); generate(true);
  assert.equal(calls.length, 0);
  context.inlineMutationBusy = false;
  generate(false); generate(true);
  assert.equal(calls.length, 2);
  assert.equal(calls[0][1].promptText, 'saved prompt');
  assert.equal(calls[0][1].referenceImage, undefined);
  assert.equal(calls[1][1].referenceImage.id, 'image');
  assert.equal((detail.match(/disabled=\{editingPromptLanguage !== undefined \|\| inlineMutationBusy\}/g) || []).length, 3);
});

test('failed generated-result save retains metadata and permits a successful retry', async () => {
  const reviewJob = { id: 'A', result_path: 'result.png' };
  const metadataDraft = { title: 'My draft', notes: 'keep notes', prompts: [{ text: 'keep prompt' }] };
  let attempt = 0;
  const accepted = [];
  const context = {
    reviewJob, metadataDraft, metadataTagsText: 'cat, art', busy: false, acceptAsNewInFlightRef: { current: false },
    ensureBatchReviewSession: () => undefined, t: value => value,
    api: { acceptGenerationJobAsNewItem: async (id, payload) => {
      assert.equal(id, 'A');
      assert.equal(payload.title, 'My draft');
      assert.equal(payload.notes, 'keep notes');
      assert.equal(payload.prompts[0].text, 'keep prompt');
      assert.deepEqual(Array.from(payload.tags), ['cat', 'art']);
      if (++attempt === 1) throw new Error('save failed');
      return { job: { ...reviewJob, status: 'accepted' }, item: { id: 'saved' } };
    } },
    setBusy: value => { context.busy = value; },
    setMessage: value => { context.message = value; },
    setReviewJob: value => { context.reviewJob = value; },
    setMetadataDraft: value => { context.metadataDraft = value; },
    setMetadataTagsText: value => { context.metadataTagsText = value; },
    setMetadataTagQuery: () => {}, invalidateGenerationRefreshRequests: () => {},
    setActiveGenerationSet: () => {}, updateGenerationJobs: () => [],
    onQueueChangedRef: { current: () => {} },
    queueAccepted: (...args) => accepted.push(args),
  };
  await handler(generation, 'acceptAsNew', context)();
  assert.equal(context.reviewJob, reviewJob);
  assert.equal(context.metadataDraft, metadataDraft);
  assert.equal(context.metadataTagsText, 'cat, art');
  assert.equal(context.busy, false);
  assert.ok(context.message);
  assert.equal(accepted.length, 0);
  await handler(generation, 'acceptAsNew', context)();
  assert.equal(attempt, 2);
  assert.equal(context.reviewJob, undefined);
  assert.equal(context.metadataDraft, undefined);
  assert.equal(accepted[0][2], 'A');
});

test('rapid save activation sends one request and unlocks after a lost response', async () => {
  let rejectRequest;
  let requests = 0;
  const context = {
    reviewJob: { id: 'result-A', result_path: 'result.png' },
    metadataDraft: { title: 'Keep this title', prompts: [{ text: 'Keep this prompt' }] },
    metadataTagsText: 'keep', busy: false, acceptAsNewInFlightRef: { current: false },
    ensureBatchReviewSession: () => undefined,
    // React state updates do not change the current render's captured busy value.
    setBusy: () => {}, setMessage: value => { context.message = value; }, t: key => key,
    api: { acceptGenerationJobAsNewItem: () => {
      requests++;
      return new Promise((_, reject) => { rejectRequest = reject; });
    } },
  };
  const save = handler(generation, 'acceptAsNew', context);
  const first = save();
  const second = save();
  const simultaneous = requests;
  rejectRequest(new Error('Connection lost'));
  // Do not await the first promise on the unfixed implementation: it was overwritten.
  await second;
  assert.equal(simultaneous, 1);
  await first;
  assert.equal(context.acceptAsNewInFlightRef.current, false);
  assert.equal(context.metadataDraft.title, 'Keep this title');
  assert.equal(context.reviewJob.result_path, 'result.png');
  assert.ok(context.message);
  const retry = save();
  assert.equal(requests, 2);
  rejectRequest(new Error('Still offline'));
  await retry;
  assert.equal(context.acceptAsNewInFlightRef.current, false);
});

test('failed provider retry and status refresh preserve the composer and result context', async () => {
  const c = draftContext({ promptText: 'Unsent changes', templateValues: { subject: 'vase' } });
  const job = { id: 'failed-A', status: 'failed', prompt_text: 'Original request' };
  Object.assign(c, {
    ensureBatchReviewSession: () => undefined, canRetryFailedJob: () => true,
    setBusy: value => { c.busy = value; }, setActiveJobId: value => { c.activeJobId = value; },
    setMessage: value => { c.message = value; },
    api: { retryGenerationJob: async () => { throw new Error('Network unavailable'); } },
    refreshJobs: async () => { throw new Error('Still offline'); },
  });
  await handler(generation, 'retryFailedJob', c)(job);
  assert.equal(c.busy, false);
  assert.equal(c.activeJobId, 'failed-A');
  assert.equal(c.promptText, 'Unsent changes');
  assert.equal(c.templateValues.subject, 'vase');
  assert.equal(c.editAttachments[0].id, 'ref');
  assert.ok(c.message);
});

test('prompt save waits for success, retains rejected drafts, and prevents overlapping edits', async () => {
  let finish;
  let requests = 0;
  const context = {
    item: { id: 'item', prompts: [{ language: 'en', text: 'old' }] },
    editingPromptLanguage: 'en', promptDraft: 'new', promptDisplayOrder: ['en', 'zh_hant', 'zh_hans'],
    inlineMutationBusyRef: { current: false }, t: value => value,
    api: { updateItem: () => { requests++; return new Promise((resolve, reject) => { finish = { resolve, reject }; }); } },
    setInlineMutationBusy: value => { context.busy = value; },
    setInlineMutationError: value => { context.error = value; },
    setEditingPromptLanguage: value => { context.editingPromptLanguage = value; },
    setPromptDraft: value => { context.promptDraft = value; },
    setItem: value => { context.item = value; }, onChanged: () => {},
  };
  for (const name of ['commitInlineUpdate', 'commitPrompt', 'cancelPromptEdit', 'startPromptEdit', 'confirmPromptEdit']) context[name] = handler(detail, name, context);
  const save = context.confirmPromptEdit();
  assert.equal(context.busy, true);
  assert.equal(context.promptDraft, 'new');
  await context.confirmPromptEdit();
  context.cancelPromptEdit();
  context.startPromptEdit('zh_hant', 'other');
  assert.equal(requests, 1);
  assert.equal(context.promptDraft, 'new');
  finish.reject(new Error('rejected'));
  await save;
  assert.ok(context.error);
  assert.equal(context.busy, false);
  assert.equal(context.editingPromptLanguage, 'en');
  assert.equal(context.promptDraft, 'new');
  const retry = context.confirmPromptEdit();
  finish.resolve({ ...context.item, prompts: [{ language: 'en', text: 'new' }] });
  await retry;
  assert.equal(requests, 2);
  assert.equal(context.editingPromptLanguage, undefined);
  assert.equal(context.promptDraft, '');
});

test('optional disclosures remain focusable in existing modal focus traps', () => {
  for (const source of [generation, detail, editor]) {
    const tree = ts.createSourceFile('component.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    let summaries = 0;
    function visit(node) {
      if (ts.isJsxOpeningElement(node) && node.tagName.getText(tree) === 'summary') {
        const parent = node.parent.parent;
        if (parent.getText(tree).includes('generation-failure-details')) return;
        summaries++;
        assert.ok(node.attributes.properties.some(attr => attr.name?.getText(tree) === 'tabIndex'));
      }
      ts.forEachChild(node, visit);
    }
    visit(tree);
    assert.ok(summaries > 0);
  }
});

test('single saved results expose only their own explicit item destination', () => {
  for (const id of ['job-A', 'job-B']) {
    const navigations = [];
    const render = handler(generation, 'renderStage', {
      selectedStageJob: { id, status: 'accepted' }, batchReviewSession: undefined,
      pendingRetryJobIds: [], acceptedTargets: { 'job-A': { id: 'saved-A', title: 'Saved A' } },
      t: value => value, jobResultUrl: () => 'result.png', isStageFullscreen: false,
      fullscreenFrameRef: {}, resultImageRef: {}, fullscreenCloseRef: {}, X: 'X',
      renderSiblingNavigation: () => null, closeStageFullscreen: () => {},
      canUseResultActions: () => false,
      openReviewTarget: (...args) => navigations.push(args),
      React: { createElement: (type, props, ...children) => ({ type, props, children }) },
    });
    const buttons = [];
    function visit(node) {
      if (!node || typeof node !== 'object') return;
      if (node.type === 'button' && node.children.includes('viewItem')) buttons.push(node);
      node.children?.forEach(visit);
    }
    visit(render());
    assert.equal(buttons.length, id === 'job-A' ? 1 : 0);
    buttons[0]?.props.onClick();
    assert.deepEqual(navigations, id === 'job-A' ? [['saved-A', 'Saved A']] : []);
  }
});

test('inline metadata editors keep the draft open until update success', async () => {
  for (const name of ['InlineEditableField', 'InlineEditableTextArea']) {
    const start = detail.indexOf(`function ${name}(`);
    const end = detail.indexOf('\nfunction ', start + 1);
    const source = detail.slice(start, end > start ? end : detail.indexOf('\nexport default', start));
    const context = { draft: 'edited', value: 'old', busy: false,
      onCommit: async () => false,
      setEditing: value => { context.editing = value; },
      setDraft: value => { context.draft = value; },
    };
    const confirm = handler(source, 'confirm', context);
    await confirm();
    assert.equal(context.editing, undefined);
    assert.equal(context.draft, 'edited');
    context.busy = true;
    handler(source, 'cancel', context)();
    assert.equal(context.draft, 'edited');
    context.busy = false;
    context.onCommit = async () => true;
    await confirm();
    assert.equal(context.editing, false);
  }
});

test('clearing translation text does not control or collapse its disclosure', () => {
  let open;
  const context = { item: {},
    initialTraditionalPrompt: () => 'existing translation', promptText: () => '',
    useState: initial => { open = initial; return [initial, () => {}]; },
  };
  // Execute the state initializer that is independent of subsequent field changes.
  handler(editor, '[translationsOpen, setTranslationsOpen]', context);
  assert.equal(open, true);
  assert.match(editor, /open=\{translationsOpen\} onToggle=/);
  assert.doesNotMatch(editor, /open=\{Boolean\(zhHantPrompt/);
});

test('loading a historical draft never claims a clipboard copy or runs a job', () => {
  let message;
  const context = {
    provider: 'provider', ensureBatchReviewSession: () => undefined,
    hasUnsubmittedDraft: () => false, setTemplateValues: () => {},
    jobAttachments: () => [{}, {}], restorableJobAttachments: () => [{}],
    jobPrompt: () => 'loaded prompt', jobAspectRatio: () => 'auto', jobQuality: () => 'medium',
    setPromptText: () => {}, setAspectRatio: () => {}, setQuality: () => {},
    setProvider: () => {}, setEditAttachments: () => {}, setHistoryReviewJobId: () => {},
    setMessage: value => { message = value; }, t: value => value,
    window: { requestAnimationFrame: () => {} },
  };
  handler(generation, 'useJobAsDraft', context)({ id: 'job' });
  assert.equal(message, 'draftLoaded draftReferencesMissing');
});

test('modal focus excludes controls disabled through a fieldset, not only their own attribute', () => {
  let focused = 0;
  const enabled = { matches: () => false, getClientRects: () => [1], focus: () => { focused++; } };
  const inheritedDisabled = {
    isConnected: true, matches: selector => selector === ':disabled', hasAttribute: () => false,
    getClientRects: () => [1], getAttribute: () => null, closest: () => null,
  };
  const document = { activeElement: enabled, body: {}, documentElement: {} };
  assert.equal(handler(modalFocus, 'isAvailableFocusTarget', { document })(inheritedDisabled), false);
  let prevented = false;
  const container = { querySelectorAll: () => [enabled, inheritedDisabled], contains: () => true };
  const trap = handler(modalFocus, 'handleModalKeyDown', { document, containerRef: { current: container }, FOCUSABLE_SELECTOR: 'button:not(:disabled)' });
  trap({ key: 'Tab', shiftKey: false, stopPropagation: () => {}, preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(focused, 1);
  prevented = false;
  trap({ key: 'Tab', shiftKey: true, stopPropagation: () => {}, preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(focused, 2);
});

test('starting a pending save moves focus off the newly disabled button into the save dialog', () => {
  const tree = ts.createSourceFile('component.tsx', generation, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let effect;
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(tree) === 'useEffect'
      && node.getText(tree).includes("querySelector<HTMLElement>('summary')")) effect = node;
    ts.forEachChild(node, visit);
  }
  visit(tree);
  assert.ok(effect, 'Pending-save focus effect must exist');
  const code = ts.transpileModule(effect.getText(tree), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  for (const [busy, reviewJob, metadataDraft, expected] of [
    [true, {}, {}, 1], [false, {}, {}, 0], [true, undefined, {}, 0], [true, {}, undefined, 0],
  ]) {
    let focused = 0;
    vm.runInNewContext(code, {
      busy, reviewJob, metadataDraft, useEffect: callback => callback(),
      saveAsNewDialogRef: { current: { querySelector: selector => {
        assert.equal(selector, 'summary');
        return { focus: options => { assert.equal(options.preventScroll, true); focused++; } };
      } } },
    });
    assert.equal(focused, expected);
  }
});

test('return language is preserved for immediate return, reset on close or preference change', () => {
  const c = {
    detailReturnLanguage: undefined, preferredLanguage: 'en',
    setDetailReturnLanguage: value => { c.detailReturnLanguage = value; },
    setPreferredLanguage: value => { c.preferredLanguage = value; },
    setDetailId: () => {}, setFocusedGenerationJobId: () => {},
    setGenerationDraft: () => {}, generationJobRequestRef: { current: 0 },
    setStandaloneGenerationOpen: () => {}, setGenerationSourceItem: () => {},
    setGenerationQueueOpen: () => {}, cancelPendingEdit: () => {},
    normalizePromptLanguage: value => value,
    window: { localStorage: { setItem: () => {} } }, PROMPT_LANGUAGE_STORAGE_KEY: 'language',
  };
  const open = handler(app, 'openGenerationFromDetail', c);
  open({ id: 'A' }, { promptLanguage: 'zh_hant' });
  handler(app, 'closeStandaloneGeneration', c)();
  assert.equal(c.detailReturnLanguage.language, 'zh_hant');
  handler(app, 'closeItemDetail', c)();
  assert.equal(c.detailReturnLanguage, undefined);
  open({ id: 'A' }, { promptLanguage: 'zh_hant' });
  handler(app, 'updatePreferredLanguage', c)('en');
  assert.equal(c.detailReturnLanguage, undefined);
  assert.equal(c.preferredLanguage, 'en');
  assert.match(app, /useEffect\(\(\) => \{ setDetailReturnLanguage\(undefined\); \}, \[detailId\]\)/);
});

test('menu opening prefers checked enabled radio, then falls back to first enabled radio', () => {
  const start = generation.indexOf('    const menu = controlTriggerRefs.current[openControl]');
  assert.ok(start > 0);
  const body = generation.slice(start, generation.indexOf('  }, [openControl]);', start));
  const code = ts.transpileModule(body, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  for (const checked of [true, false]) {
    let focused;
    const menu = { querySelector: selector => {
      assert.ok(selector.includes(':not(:disabled)'));
      return selector.includes('[aria-checked="true"]')
        ? (checked ? { focus: () => { focused = '16:9'; } } : null)
        : { focus: () => { focused = 'Auto'; } };
    } };
    vm.runInNewContext(code, { openControl: 'aspect', controlTriggerRefs: { current: { aspect: { parentElement: { querySelector: () => menu } } } } });
    assert.equal(focused, checked ? '16:9' : 'Auto');
  }
});
