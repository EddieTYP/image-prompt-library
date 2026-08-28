import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import test, { after, before } from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const FRONTEND_ROOT = fileURLToPath(new URL('../frontend', import.meta.url));
let vite;
let ExploreView;
let CardsView;
let ItemCard;
let GenerationQueueDrawer;
let BatchActionDialog;
let groupGenerationQueueJobs;
let generationQueueBatchCounts;

const labels = {
  addFirstPrompt: 'Add your first prompt',
  allReferences: 'All references',
  collections: 'Collections',
  copyPrompt: 'Copy prompt',
  explore: 'Explore',
  libraryEmptyHelp: 'Add a prompt',
  libraryEmptyTitle: 'Your library is empty',
  more: 'Show more',
  noCollectionsFound: 'No collections found',
  noImage: 'No image',
  noMatchingPrompts: 'No matching prompts',
  noMatchingPromptsHelp: 'Try another search',
  referencesShown: 'references',
  itemActions: 'Item actions',
  searchResults: 'Search results',
  sortChip: 'Sort',
  sortByUpdated: 'Recently updated',
  sortByCreated: 'Recently added',
  sortByOldest: 'Oldest first',
  sortByTitle: 'Title A–Z',
  sortByTitleDesc: 'Title Z-A',
  sortBySource: 'Source A-Z',
  sortByModel: 'Model A-Z',
  favorite: 'Favorite',
  unfavorite: 'Unfavorite',
  edit: 'Edit',
  moreActions: 'More actions',
  batchMoreActions: 'More',
  saved: 'Saved',
  workQueue: 'Work queue',
  generationQueue: 'Generation queue',
  queueLoading: 'Loading work queue…',
  noGenerationActivity: 'No generation activity',
  generationActivityHelp: 'New and completed jobs will appear here.',
  showImage: 'Show image',
  batchTagTitle: 'Tag selected references',
  batchMoveTitle: 'Move selected references',
  selectedReferences: 'selected',
  searchOrCreateTags: 'Search or create tags',
  searchCollections: 'Search collections',
  selectedTags: 'Selected tags',
  createTag: 'Create “${tag}”',
  noTagsFound: 'No tags found',
  applyTags: 'Apply tags',
  moveReferences: 'Move references',
  close: 'Close',
  cancel: 'Cancel',
  saving: 'Saving…',
};
const t = key => labels[key] || key;

function item(index, cluster) {
  const imagePath = `media/item-${index}.webp`;
  return {
    id: `item-${index}`,
    title: `Item ${index}`,
    slug: `item-${index}`,
    model: 'gpt-image-1',
    cluster,
    tags: [],
    prompts: [{ id: `prompt-${index}`, item_id: `item-${index}`, language: 'en', text: `Prompt ${index}`, is_primary: true }],
    first_image: { id: `image-${index}`, item_id: `item-${index}`, original_path: imagePath, preview_path: imagePath, thumb_path: imagePath, width: index % 2 ? 600 : 900, height: index % 2 ? 900 : 600 },
    rating: 0,
    favorite: false,
    archived: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function render(props = {}) {
  return renderToStaticMarkup(React.createElement(ExploreView, {
    t,
    clusters: [],
    items: [],
    total: 0,
    hasActiveSearch: false,
    searchQuery: '',
    loading: false,
    sort: 'updated_desc',
    onSort: () => undefined,
    onOpenCollection: () => undefined,
    onOpen: () => undefined,
    onCopyPrompt: () => undefined,
    ...props,
  }));
}

function renderCards(props = {}) {
  return renderToStaticMarkup(React.createElement(CardsView, {
    t,
    items: [],
    loading: false,
    total: 0,
    sort: 'updated_desc',
    onSort: () => undefined,
    onClearCluster: () => undefined,
    onOpen: () => undefined,
    onCopyPrompt: () => undefined,
    ...props,
  }));
}

test('loading scopes render neutral skeletons instead of false empty guidance', () => {
  const exploreHtml = render({ loading: true });
  const cardsHtml = renderCards({ loading: true, emptyMode: undefined });
  const staleCluster = { id: 'stale', name: 'Previous results', count: 2, preview_images: [] };
  const searchHtml = render({
    loading: true,
    hasActiveSearch: true,
    searchQuery: 'poster',
    clusters: [staleCluster],
  });

  for (const html of [exploreHtml, cardsHtml, searchHtml]) {
    assert.match(html, /class="content-loading-state"/);
    assert.doesNotMatch(html, /Your library is empty|No matching prompts|No collections found/);
  }
});

before(async () => {
  vite = await createServer({
    root: FRONTEND_ROOT,
    configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true },
  });
  ({ default: ExploreView } = await vite.ssrLoadModule('/src/components/ExploreView.tsx'));
  ({ default: CardsView } = await vite.ssrLoadModule('/src/components/CardsView.tsx'));
  ({ default: ItemCard } = await vite.ssrLoadModule('/src/components/ItemCard.tsx'));
  ({ default: GenerationQueueDrawer, groupGenerationQueueJobs, generationQueueBatchCounts } = await vite.ssrLoadModule('/src/components/GenerationQueueDrawer.tsx'));
  ({ default: BatchActionDialog } = await vite.ssrLoadModule('/src/components/BatchActionDialog.tsx'));
});

after(async () => {
  await vite?.close();
});

test('batch tag and move actions use in-app searchable dialogs', async () => {
  const shared = {
    selectedCount: 3,
    busy: false,
    t,
    onClose: () => {},
    onApplyTags: async () => {},
    onApplyCollection: async () => {},
  };
  const tags = [{ id: 'tag-1', name: 'poster', kind: 'user', count: 12 }];
  const clusters = [{ id: 'cluster-1', name: 'Campaigns', count: 7, preview_images: [] }];
  const tagHtml = renderToStaticMarkup(React.createElement(BatchActionDialog, { ...shared, mode: 'tags', tags, clusters }));
  const moveHtml = renderToStaticMarkup(React.createElement(BatchActionDialog, { ...shared, mode: 'move', tags, clusters }));

  assert.match(tagHtml, /role="dialog"/);
  assert.match(tagHtml, /Search or create tags/);
  assert.match(tagHtml, /#poster/);
  assert.match(tagHtml, /Apply tags/);
  assert.match(moveHtml, /role="radiogroup"/);
  assert.match(moveHtml, /Search collections/);
  assert.match(moveHtml, /Campaigns/);
  assert.match(moveHtml, /Move references/);

  const app = await readFile(`${ROOT}/frontend/src/App.tsx`, 'utf8');
  const styles = await readFile(`${ROOT}/frontend/src/styles.css`, 'utf8');
  assert.doesNotMatch(app, /prompt\(t\('tagSelectedReferences'\)\)/);
  assert.doesNotMatch(app, /prompt\(t\('moveSelectedReferences'\)\)/);
  assert.match(app, /<BatchActionDialog/);
  assert.match(styles, /@media\(max-width:760px\)\{\.modal-backdrop\.batch-action-backdrop\{align-items:flex-end/);
});

test('Explore directory lists only non-empty Collections with uncropped preview metadata', () => {
  const activeCluster = {
    id: 'active',
    name: 'Portraits',
    count: 60,
    preview_images: ['media/item-0.webp', 'media/item-1.webp', 'media/item-2.webp'],
    preview_item_ids: ['item-0', 'item-1', 'item-2'],
  };
  const emptyCluster = { id: 'empty', name: 'Empty Collection', count: 0, preview_images: [] };
  const items = Array.from({ length: 60 }, (_, index) => item(index, activeCluster));
  const html = render({ clusters: [activeCluster, emptyCluster], items, total: 60 });

  assert.match(html, /class="explore-directory"/);
  assert.equal((html.match(/<h1\b/g) || []).length, 1);
  assert.match(html, /<h1>Collections<\/h1>/);
  assert.match(html, /class="scope-count"[\s\S]*?>1<span class="sr-only"> Collections<\/span>/);
  assert.doesNotMatch(html, /<select\b/);
  assert.match(html, /Portraits/);
  assert.doesNotMatch(html, /Empty Collection/);
  assert.equal((html.match(/class="explore-collection-preview"/g) || []).length, 3);
  assert.equal((html.match(/data-card-id=/g) || []).length, 3);
  assert.match(html, /<article class="explore-collection-card">/);
  assert.match(html, /<button type="button" class="explore-collection-heading"/);
  assert.match(html, /width="900" height="600"/);
  assert.match(html, /flex-grow:1\.5/);
  assert.doesNotMatch(html, /constellation/);
});

test('Explore preview IDs stay clickable outside the loaded item window and disambiguate shared image paths', () => {
  const activeCluster = {
    id: 'active',
    name: 'Portraits',
    count: 1002,
    preview_images: ['media/shared.webp', 'media/shared.webp', 'media/outside.webp'],
    preview_item_ids: ['item-0', 'item-1', 'item-1001'],
  };
  const first = item(0, activeCluster);
  const second = item(1, activeCluster);
  first.first_image.original_path = 'media/shared.webp';
  first.first_image.preview_path = 'media/shared.webp';
  first.first_image.thumb_path = 'media/shared.webp';
  second.first_image.original_path = 'media/shared.webp';
  second.first_image.preview_path = 'media/shared.webp';
  second.first_image.thumb_path = 'media/shared.webp';

  const html = render({ clusters: [activeCluster], items: [first, second], total: 1002 });

  assert.equal((html.match(/class="explore-collection-preview"/g) || []).length, 3);
  for (const id of ['item-0', 'item-1', 'item-1001']) {
    assert.match(html, new RegExp(`data-card-id="${id}"`));
  }
  assert.doesNotMatch(html, /class="explore-collection-preview"[^>]*aria-hidden="true"/);
});

test('Explore search feed renders the first 48 natural-ratio cards and keeps management actions out', () => {
  const cluster = { id: 'active', name: 'Portraits', count: 60, preview_images: [] };
  const items = Array.from({ length: 60 }, (_, index) => item(index, cluster));
  const html = render({ clusters: [cluster], items, total: 60, hasActiveSearch: true, searchQuery: 'portrait' });

  assert.match(html, /class="explore-feed"/);
  assert.equal((html.match(/<h1\b/g) || []).length, 1);
  assert.match(html, /<h1>Search results<\/h1>/);
  assert.match(html, /class="scope-count"[\s\S]*?>60<span class="sr-only"> references<\/span>/);
  assert.match(html, /<select\b[^>]*aria-label="Sort"/);
  assert.equal((html.match(/class="item-card /g) || []).length, 48);
  assert.match(html, /Item 47/);
  assert.doesNotMatch(html, /Item 48/);
  assert.match(html, /aria-label="Copy prompt"/);
  assert.match(html, /aria-label="Download"/);
  assert.doesNotMatch(html, /aria-label="Edit"/);
  assert.doesNotMatch(html, /card-select-action/);
  assert.match(html, /Show more/);
});

test('active search uses the Explore feed while unclustered items do not claim the library is empty', () => {
  const searchHtml = render({ hasActiveSearch: true, searchQuery: 'poster' });
  assert.match(searchHtml, /class="explore-feed"/);
  assert.match(searchHtml, /<h1>Search results<\/h1>/);
  assert.match(searchHtml, /No matching prompts/);

  const unclusteredHtml = render({ items: [item(0)], total: 1 });
  assert.match(unclusteredHtml, /No collections found/);
  assert.match(unclusteredHtml, /class="scope-count"[\s\S]*?>0<span class="sr-only"> Collections<\/span>/);
  assert.doesNotMatch(unclusteredHtml, /Your library is empty/);
});

test('Library keeps one contextual scope, sort, and first-run count', () => {
  const activeItem = item(0);
  const html = renderCards({ items: [activeItem], total: 1 });

  assert.equal((html.match(/<h1\b/g) || []).length, 1);
  assert.match(html, /<h1>All references<\/h1>/);
  assert.match(html, /class="scope-count"[\s\S]*?>1<span class="sr-only"> references<\/span>/);
  assert.match(html, /class="scope-sort-control"[\s\S]*?<span class="scope-sort-prefix">Sort<\/span>[\s\S]*?<span class="scope-sort-picker">[\s\S]*?<select\b/);
  assert.match(html, /<label class="scope-sort-control" for="[^"]+">[\s\S]*?<select id="[^"]+" class="scope-sort-select"/);
  assert.match(html, /<select\b[^>]*aria-label="Sort"/);

  const firstRunHtml = renderCards({ emptyMode: 'first-run' });
  assert.match(firstRunHtml, /<h1>All references<\/h1>/);
  assert.match(firstRunHtml, /class="scope-count"[\s\S]*?>0<span class="sr-only"> references<\/span>/);
  assert.match(firstRunHtml, /<select\b[^>]*aria-label="Sort"/);
});

test('empty work queue uses one composed state instead of four empty sections', () => {
  const html = renderToStaticMarkup(React.createElement(GenerationQueueDrawer, {
    t,
    open: true,
    onOpen: () => undefined,
    onClose: () => undefined,
    onOpenJob: () => undefined,
    onOpenProviders: () => undefined,
  }));

  assert.match(html, /class="generation-queue-drawer open"/);
  assert.match(html, /aria-expanded="true"/);
  assert.match(html, /aria-controls="generation-work-queue"/);
  assert.match(html, /id="generation-work-queue"/);
  assert.match(html, /aria-labelledby="generation-work-queue-title"/);
  assert.match(html, /<h2 id="generation-work-queue-title">Work queue<\/h2>/);
  assert.equal((html.match(/<h2\b/g) || []).length, 1);
  assert.doesNotMatch(html, /drawer-eyebrow/);
  assert.doesNotMatch(html, /<h2>Generation queue<\/h2>/);
  assert.match(html, /Loading work queue…/);
  assert.doesNotMatch(html, /No generation activity/);
  for (const heading of ['In progress', 'Ready for review', 'Needs attention', 'Recent']) {
    assert.doesNotMatch(html, new RegExp(`<h3>${heading}<\\/h3>`));
  }
});

test('work queue batch cards use the loaded jobs page for capped previews and persistent counts', async () => {
  const [queueDrawer, styles] = await Promise.all([
    readFile(`${ROOT}/frontend/src/components/GenerationQueueDrawer.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/styles.css`, 'utf8'),
  ]);
  assert.match(queueDrawer, /groupGenerationQueueJobs\(jobs/);
  assert.match(queueDrawer, /slice\(0, previewLimit\)/);
  assert.match(queueDrawer, /loading="lazy" decoding="async"/);
  assert.match(queueDrawer, /className="generation-set-card generation-queue-batch-card"[\s\S]*?className="generation-queue-batch-previews"[\s\S]*?className="generation-set-actions"/);
  assert.match(styles, /generation-queue-batch-previews img\{[^}]*object-fit:contain/);
  assert.match(styles, /\.generation-queue-batch-card\{[^}]*display:grid;[^}]*grid-template-columns:minmax\(0,1fr\) auto;[^}]*grid-template-areas:"head actions" "previews actions" "counts actions"/);
  assert.match(styles, /\.generation-queue-batch-card > \.generation-queue-batch-previews\{[^}]*grid-area:previews;[^}]*overflow:visible/);
  assert.match(styles, /\.generation-queue-batch-card > \.generation-set-actions\{[^}]*grid-area:actions;[^}]*flex-direction:column/);
  assert.match(styles, /\.generation-queue-batch-previews img\{[^}]*width:44px;[^}]*height:44px;[^}]*object-fit:contain/);
  assert.match(styles, /\.generation-queue-batch-placeholder\{[^}]*width:44px;[^}]*height:44px/);
  assert.match(styles, /\.generation-queue-batch-card \.generation-cancel-remaining\{[^}]*min-height:44px/);
  assert.match(styles, /\.generation-open-set\{[^}]*min-height:44px/);
  assert.match(queueDrawer, /generationQueueStatusCounts\(jobs, statusCounts\)/);
  assert.match(queueDrawer, /const queueStatusItems = \[[\s\S]*?\]\.filter\(item => item\.count > 0\)/);
  assert.match(queueDrawer, /<ul className="queue-summary generation-queue-persistent-counts">[\s\S]*?<li key=\{item\.key\}/);
  assert.doesNotMatch(queueDrawer, /aria-label=\{t\('queueSummary'\)\}/);
  assert.match(queueDrawer, /resolveGenerationRetryGroup/);
  assert.match(queueDrawer, /mapGenerationRetryJob/);
  assert.match(queueDrawer, /retryAdjustments/);
  assert.match(queueDrawer, /active: set\.queued \+ set\.running/);
  assert.match(queueDrawer, /if \(statusBucket\) counts\[statusBucket\] = Math\.max\(0, counts\[statusBucket\] \+ delta\)/);
  assert.match(queueDrawer, /summary\.active > 0/);
  assert.match(queueDrawer, /generationQueueBatchCounts\(group, set\)/);
  assert.match(queueDrawer, /if \(group\.total > group\.jobs\.length\)[\s\S]*?api\.generationSet\(group\.generationGroupId\)[\s\S]*?groupGenerationQueueJobs\(mergedJobs\)/);
  assert.match(queueDrawer, /let expansionError: unknown[\s\S]*?catch \(error\) \{[\s\S]*?expansionError = error/);
  assert.match(queueDrawer, /rememberGenerationReviewOpenContext\(job\.id/);
  assert.match(queueDrawer, /open \?[\s\S]*?group\.previews\.map/);
  assert.match(queueDrawer, /queueSaved/);
  assert.match(queueDrawer, /queueDiscarded/);
  assert.match(queueDrawer, /queueCancelled/);
  assert.doesNotMatch(queueDrawer, /function generationSetStatusText/);
});

test('work queue batch previews exclude stale terminal result paths', () => {
  const jobs = [
    { id: 'ready', status: 'succeeded', result_path: 'generation-results/ready/result.png', generation_group_id: 'group', generation_group_index: 0, generation_group_size: 4, metadata: {} },
    { id: 'saved', status: 'accepted', result_path: 'generation-results/saved/result.png', generation_group_id: 'group', generation_group_index: 1, generation_group_size: 4, metadata: {} },
    { id: 'failed', status: 'failed', result_path: 'generation-results/failed/stale.png', generation_group_id: 'group', generation_group_index: 2, generation_group_size: 4, metadata: {} },
    { id: 'cancelled', status: 'cancelled', result_path: 'generation-results/cancelled/stale.png', generation_group_id: 'group', generation_group_index: 3, generation_group_size: 4, metadata: {} },
  ];

  const [group] = groupGenerationQueueJobs(jobs);
  assert.deepEqual(group.previews.map(job => job.id), ['ready', 'saved']);
  assert.equal(group.previewOverflow, 0);
});

test('work queue batch counts trust canonical backend counts for grouped retry replacements', () => {
  const groupFields = { generation_group_id: 'group', generation_group_size: 3 };
  const jobs = [
    { id: 'slot-1', status: 'succeeded', generation_group_index: 1, metadata: {}, ...groupFields },
    { id: 'original', status: 'failed', generation_group_index: 2, metadata: { retried_by_generation_job_id: 'retry-1' }, ...groupFields },
    { id: 'retry-1', status: 'failed', generation_group_index: 2, metadata: { retry_of_generation_job_id: 'original', retried_by_generation_job_id: 'retry-2' }, ...groupFields },
    { id: 'retry-2', status: 'queued', generation_group_index: 2, metadata: { retry_of_generation_job_id: 'retry-1' }, ...groupFields },
    { id: 'slot-3', status: 'accepted', generation_group_index: 3, metadata: {}, ...groupFields },
  ];
  const [group] = groupGenerationQueueJobs(jobs);
  const counts = generationQueueBatchCounts(group, {
    generation_group_id: 'group',
    provider: 'openai_codex_oauth_native',
    created_at: '2026-01-01T00:00:00Z',
    total: 3,
    queued: 1,
    running: 0,
    succeeded: 1,
    failed: 0,
    accepted: 1,
    discarded: 0,
    cancelled: 0,
    completed: 2,
    remaining: 1,
    jobs: [],
  });

  assert.deepEqual(group.jobs.map(job => job.id), ['slot-1', 'retry-2', 'slot-3']);
  assert.deepEqual(group.retryAdjustments, []);
  assert.deepEqual(counts, {
    total: 3,
    active: 1,
    waitingReview: 1,
    accepted: 1,
    discarded: 0,
    failed: 0,
    cancelled: 0,
  });
});

test('work queue batch counts include legacy retry replacements not counted by the backend set', () => {
  const groupFields = { generation_group_id: 'group', generation_group_size: 3 };
  const jobs = [
    { id: 'slot-1', status: 'succeeded', generation_group_index: 1, metadata: {}, ...groupFields },
    { id: 'original', status: 'failed', generation_group_index: 2, metadata: { retried_by_generation_job_id: 'retry' }, ...groupFields },
    {
      id: 'retry',
      status: 'queued',
      metadata: {
        retry_of_generation_job_id: 'original',
        retry_generation_group_id: 'group',
        retry_generation_group_index: 2,
        retry_generation_group_size: 3,
      },
    },
    { id: 'slot-3', status: 'accepted', generation_group_index: 3, metadata: {}, ...groupFields },
  ];
  const [group] = groupGenerationQueueJobs(jobs);
  const counts = generationQueueBatchCounts(group, {
    generation_group_id: 'group',
    provider: 'openai_codex_oauth_native',
    created_at: '2026-01-01T00:00:00Z',
    total: 3,
    queued: 0,
    running: 0,
    succeeded: 1,
    failed: 1,
    accepted: 1,
    discarded: 0,
    cancelled: 0,
    completed: 3,
    remaining: 0,
    jobs: [],
  });

  assert.deepEqual(group.jobs.map(job => job.id), ['slot-1', 'retry', 'slot-3']);
  assert.deepEqual(counts, {
    total: 3,
    active: 1,
    waitingReview: 1,
    accepted: 1,
    discarded: 0,
    failed: 0,
    cancelled: 0,
  });
});

test('work queue batch counts replace a paginated-out failed retry ancestor', () => {
  const groupFields = { generation_group_id: 'group', generation_group_size: 3 };
  const jobs = [
    { id: 'slot-1', status: 'succeeded', generation_group_index: 1, metadata: {}, ...groupFields },
    {
      id: 'retry',
      status: 'queued',
      metadata: {
        retry_of_generation_job_id: 'omitted-original',
        retry_reason: 'failed_retry',
        retry_generation_group_id: 'group',
        retry_generation_group_index: 2,
        retry_generation_group_size: 3,
      },
    },
    { id: 'slot-3', status: 'accepted', generation_group_index: 3, metadata: {}, ...groupFields },
  ];
  const [group] = groupGenerationQueueJobs(jobs);
  const counts = generationQueueBatchCounts(group, {
    generation_group_id: 'group',
    provider: 'openai_codex_oauth_native',
    created_at: '2026-01-01T00:00:00Z',
    total: 3,
    queued: 0,
    running: 0,
    succeeded: 1,
    failed: 1,
    accepted: 1,
    discarded: 0,
    cancelled: 0,
    completed: 3,
    remaining: 0,
    jobs: [],
  });

  assert.deepEqual(group.jobs.map(job => job.id), ['slot-1', 'retry', 'slot-3']);
  assert.deepEqual(counts, {
    total: 3,
    active: 1,
    waitingReview: 1,
    accepted: 1,
    discarded: 0,
    failed: 0,
    cancelled: 0,
  });
});

test('work queue batch counts do not readjust canonical grouped retry counts', () => {
  const groupFields = { generation_group_id: 'group', generation_group_index: 2, generation_group_size: 3 };
  const jobs = [
    {
      id: 'retry-1',
      status: 'failed',
      metadata: {
        retry_of_generation_job_id: 'omitted-original',
        retry_reason: 'failed_retry',
        retried_by_generation_job_id: 'retry-2',
      },
      ...groupFields,
    },
    {
      id: 'retry-2',
      status: 'queued',
      metadata: { retry_of_generation_job_id: 'retry-1', retry_reason: 'failed_retry' },
      ...groupFields,
    },
  ];
  const [group] = groupGenerationQueueJobs(jobs);
  const counts = generationQueueBatchCounts(group, {
    generation_group_id: 'group',
    provider: 'openai_codex_oauth_native',
    created_at: '2026-01-01T00:00:00Z',
    total: 3,
    queued: 1,
    running: 0,
    succeeded: 1,
    failed: 0,
    accepted: 1,
    discarded: 0,
    cancelled: 0,
    completed: 2,
    remaining: 1,
    jobs: [],
  });

  assert.deepEqual(group.jobs.map(job => job.id), ['retry-2']);
  assert.deepEqual(counts, {
    total: 3,
    active: 1,
    waitingReview: 1,
    accepted: 1,
    discarded: 0,
    failed: 0,
    cancelled: 0,
  });
});

test('work queue batch counts keep canonical counts when retry ancestors are paginated out', () => {
  const groupFields = { generation_group_id: 'group', generation_group_size: 3 };
  const jobs = [
    { id: 'slot-1', status: 'succeeded', generation_group_index: 1, metadata: {}, ...groupFields },
    {
      id: 'retry-2',
      status: 'succeeded',
      generation_group_index: 2,
      metadata: { retry_of_generation_job_id: 'omitted-retry-1', retry_reason: 'failed_retry' },
      ...groupFields,
    },
    { id: 'slot-3', status: 'accepted', generation_group_index: 3, metadata: {}, ...groupFields },
  ];
  const [group] = groupGenerationQueueJobs(jobs);
  const counts = generationQueueBatchCounts(group, {
    generation_group_id: 'group',
    provider: 'openai_codex_oauth_native',
    created_at: '2026-01-01T00:00:00Z',
    total: 3,
    queued: 0,
    running: 0,
    succeeded: 2,
    failed: 0,
    accepted: 1,
    discarded: 0,
    cancelled: 0,
    completed: 3,
    remaining: 0,
    jobs: [],
  });

  assert.deepEqual(counts, {
    total: 3,
    active: 0,
    waitingReview: 2,
    accepted: 1,
    discarded: 0,
    failed: 0,
    cancelled: 0,
  });
});

test('work queue batch counts keep an omitted legacy ancestor when retry metadata cannot identify its status', () => {
  const jobs = [{
    id: 'retry',
    status: 'queued',
    metadata: {
      retry_of_generation_job_id: 'omitted-original',
      retry_generation_group_id: 'group',
      retry_generation_group_index: 2,
      retry_generation_group_size: 3,
    },
  }];
  const [group] = groupGenerationQueueJobs(jobs);
  const counts = generationQueueBatchCounts(group, {
    generation_group_id: 'group',
    provider: 'openai_codex_oauth_native',
    created_at: '2026-01-01T00:00:00Z',
    total: 3,
    queued: 0,
    running: 0,
    succeeded: 1,
    failed: 1,
    accepted: 1,
    discarded: 0,
    cancelled: 0,
    completed: 3,
    remaining: 0,
    jobs: [],
  });

  assert.equal(counts.active, 1);
  assert.equal(counts.failed, 1);
});

test('work queue keeps malformed cross-group retry ancestors visible', () => {
  const jobs = [
    {
      id: 'group-one-original',
      status: 'failed',
      generation_group_id: 'group-one',
      generation_group_index: 1,
      generation_group_size: 3,
      metadata: { retried_by_generation_job_id: 'group-two-retry' },
    },
    {
      id: 'group-two-retry',
      status: 'queued',
      generation_group_id: 'group-two',
      generation_group_index: 1,
      generation_group_size: 3,
      metadata: { retry_of_generation_job_id: 'group-one-original' },
    },
  ];

  const groups = groupGenerationQueueJobs(jobs);
  assert.deepEqual(groups.map(group => [group.generationGroupId, group.jobs.map(job => job.id)]), [
    ['group-one', ['group-one-original']],
    ['group-two', ['group-two-retry']],
  ]);
});

test('generation review rehydrates a queue-opened batch context and mapped retry chain', async () => {
  const [generation, siblings] = await Promise.all([
    readFile(`${ROOT}/frontend/src/components/GenerationPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/utils/generationSiblings.ts`, 'utf8'),
  ]);
  assert.match(generation, /generationReviewOpenContext\(initialJobId\)/);
  assert.match(generation, /mapGenerationRetryJobs\(item \? result\.jobs/);
  assert.match(generation, /hydratedContextJobs/);
  assert.match(generation, /generation_group_id: freshJob\.generation_group_id \|\| contextJob\.generation_group_id/);
  assert.match(generation, /mapGenerationRetryJobs\(refreshed\.jobs\)/);
  assert.match(siblings, /resolveGenerationRetryGroup/);
  assert.match(siblings, /ancestorIds/);
  assert.match(siblings, /generationReviewOpenContexts/);
});

test('generation review never resurrects deleted results or stale active context status', async () => {
  const [generation, siblings] = await Promise.all([
    readFile(`${ROOT}/frontend/src/components/GenerationPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/utils/generationSiblings.ts`, 'utf8'),
  ]);
  assert.match(generation, /!\['discarded', 'cancelled', 'failed'\]\.includes\(candidate\.status\)/);
  assert.match(generation, /job\.result_path && !\['discarded', 'cancelled', 'failed'\]\.includes\(job\.status\)/);
  assert.match(generation, /selectedStageJob\?\.result_path && !\['discarded', 'cancelled', 'failed'\]\.includes\(selectedStageJob\.status\)/);
  assert.match(generation, /MAX_OPEN_CONTEXT_ACTIVE_FETCHES/);
  assert.match(generation, /activeContextJobsMissingFromPage/);
  assert.match(generation, /api\.generationJob\(contextJob\.id\)/);
  assert.match(generation, /contextHydrationFailedIds/);
  assert.match(generation, /activeContextFetchIds\.has\(contextJob\.id\)/);
  assert.match(generation, /preservedIds\.has\(job\.id\) && !contextHydrationFailedIds\.has\(job\.id\)/);
  assert.match(siblings, /\['discarded', 'cancelled', 'failed'\]\.includes\(currentJob\.status\)/);
  assert.match(siblings, /\['discarded', 'cancelled', 'failed'\]\.includes\(job\.status\)/);
});

test('detail gallery thumbnails prefer display images and contain them in the rail box', async () => {
  const [detail, styles] = await Promise.all([
    readFile(`${ROOT}/frontend/src/components/ItemDetailModal.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/styles.css`, 'utf8'),
  ]);
  assert.match(detail, /imageDisplayPath\(img\) \|\| imageThumbnailPath\(img\)/);
  assert.match(styles, /\.image-gallery-thumb\{[^}]*width:64px;[^}]*height:64px/);
  assert.match(styles, /\.image-gallery-thumb img\{[^}]*width:100%;[^}]*height:100%;[^}]*min-width:0;[^}]*min-height:0;[^}]*max-width:100%;[^}]*max-height:100%;[^}]*object-fit:contain/);
  assert.match(styles, /\.image-gallery-thumb img\{[^}]*border:0;[^}]*border-radius:0/);
  assert.doesNotMatch(styles, /\.image-gallery-thumb img\{[^}]*border:2px solid white/);
});

test('batch review leaves a resolved stage and exposes session-only item targets', async () => {
  const generation = await readFile(`${ROOT}/frontend/src/components/GenerationPanel.tsx`, 'utf8');
  assert.match(generation, /setHistoryReviewJobId\(job\.id\);[\s\S]*?setActiveJobId\(job\.id\)/);
  assert.match(generation, /targetItemId: result\.item\?\.id/);
  assert.match(generation, /generation-stage-outcome status-discarded/);
  assert.match(generation, /pendingRetryJobIds\.includes\(selectedStageJob\.id\) \? t\('reviewRetrying'\)/);
  assert.match(generation, /retainPendingRetryJobIds\(current, jobs\)/);
  assert.match(generation, /openReviewTarget\(reviewTargetId, reviewTargetTitle\)/);
});

test('generation composer exposes the refreshed recommended model list', async () => {
  const [generation, translations, styles] = await Promise.all([
    readFile(`${ROOT}/frontend/src/components/GenerationPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/utils/i18n.ts`, 'utf8'),
    readFile(`${ROOT}/frontend/src/styles.css`, 'utf8'),
  ]);

  assert.match(generation, /\['gpt-5\.6-terra', 'gpt-5\.6-sol', 'gpt-5\.6-luna'\]/);
  assert.match(generation, /recommendedOrchestratorModel[\s\S]*?generationRecommended/);
  assert.equal((generation.match(/generation-control-option-check/g) || []).length, 3);
  assert.match(generation, /role="menuitemradio" aria-checked=\{selected\}[\s\S]*?generation-control-option-label/);
  assert.match(generation, /generation-model-option-copy[\s\S]*?generation-control-option-check/);
  assert.match(styles, /\.generation-model-option-copy\{display:grid;gap:2px/);
  assert.match(styles, /\.generation-control-popover button\{[^}]*font-size:13px;[^}]*font-weight:700/);
  assert.match(styles, /\.generation-control-popover button\.is-selected\{background:rgb\(var\(--studio-accent-rgb\) \/ \.1\);color:var\(--studio-ink\);font-weight:750;box-shadow:none/);
  assert.doesNotMatch(styles, /box-shadow:inset 3px 0 0 var\(--studio-accent\)/);
  assert.equal((translations.match(/generationRecommended:/g) || []).length, 3);
});

test('generation cancel action keeps its text inside a readable pill', async () => {
  const styles = await readFile(`${ROOT}/frontend/src/styles.css`, 'utf8');

  assert.match(styles, /\.generation-stage-actions\.generation-cancel-actions\{[^}]*flex-wrap:nowrap/);
  assert.match(styles, /\.generation-cancel-actions \.stage-action\.danger\{width:auto;min-width:78px;[^}]*padding:0 15px/);
});

test('Library card keeps desktop actions and exposes a compact mobile More trigger', () => {
  const html = renderToStaticMarkup(React.createElement(ItemCard, {
    t,
    item: item(0),
    onOpen: () => undefined,
    onCopyPrompt: () => undefined,
    onFavorite: () => undefined,
    onEdit: () => undefined,
  }));

  assert.equal((html.match(/class="hover-action(?: [^"]+)?"/g) || []).length, 5);
  for (const label of ['Copy prompt', 'Download', 'Favorite', 'Edit', 'More actions']) {
    assert.match(html, new RegExp(`aria-label="${label}"`));
  }
  assert.match(html, /class="card-actions" role="group" aria-label="Item actions"/);
  assert.match(html, /class="hover-action card-action-more"[^>]*aria-haspopup="menu"[^>]*aria-expanded="false"/);
  assert.match(html, /class="card-open-hit"/);
  assert.doesNotMatch(html, /<article[^>]*role="button"/);
  assert.match(html, /width="900" height="600"/);
  assert.match(html, /style="aspect-ratio:900 \/ 600"/);

  const selectingHtml = renderToStaticMarkup(React.createElement(ItemCard, {
    t,
    item: item(0),
    onOpen: () => undefined,
    onToggleSelection: () => undefined,
    onCopyPrompt: () => undefined,
    isSelecting: true,
  }));
  assert.match(selectingHtml, /class="card-open-hit"[^>]*tabindex="-1"[^>]*aria-hidden="true"/);
  assert.equal((selectingHtml.match(/aria-label="Select Item 0"/g) || []).length, 1);
});

test('Config provider actions clear busy on close without accepting stale results', async () => {
  const config = await readFile(`${ROOT}/frontend/src/components/ConfigPanel.tsx`, 'utf8');

  assert.match(config, /if \(!open\) \{\s*providersRequestRef\.current \+= 1;\s*providerActionRequestRef\.current \+= 1;\s*setProviderBusy\(false\);\s*return;/);
  assert.match(config, /useEffect\(\(\) => \(\) => \{\s*providersRequestRef\.current \+= 1;\s*providerActionRequestRef\.current \+= 1;\s*closeMotionCleanupRef\.current\?\.\(\);\s*\}, \[\]\);/);
  assert.match(config, /const closePanel = \(\) => \{\s*providersRequestRef\.current \+= 1;\s*providerActionRequestRef\.current \+= 1;\s*setProviderBusy\(false\);[\s\S]*?onClose\(\);/);
  assert.equal((config.match(/if \(providerActionRequestRef\.current === requestId\) setProviderBusy\(false\);/g) || []).length, 3);
});

test('Explore wiring preserves Library management, semantic appearance, and restrained motion', async () => {
  const [app, cards, explore, config, styles, translations, toggle, topBar, generationPanel, queueDrawer, editorModal, suggestedTitleField, modalFocus, appearance, itemCard] = await Promise.all([
    readFile(`${ROOT}/frontend/src/App.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/CardsView.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ExploreView.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ConfigPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/styles.css`, 'utf8'),
    readFile(`${ROOT}/frontend/src/utils/i18n.ts`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ViewToggle.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/TopBar.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/GenerationPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/GenerationQueueDrawer.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ItemEditorModal.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/SuggestedTitleField.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/hooks/useModalFocus.ts`, 'utf8'),
    readFile(`${ROOT}/frontend/src/utils/appearance.ts`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ItemCard.tsx`, 'utf8'),
  ]);

  assert.match(app, /nextView !== 'cards'/);
  assert.match(app, /view === 'cards' && selectionMode/);
  assert.match(app, /className="selection-toolbar-button selection-toolbar-more-trigger"[\s\S]*?aria-haspopup="menu"[\s\S]*?aria-expanded=\{selectionActionsOpen\}/);
  assert.match(app, /className="selection-toolbar-menu" role="menu"/);
  assert.match(app, /className="selection-toolbar-delete selection-toolbar-desktop-delete"/);
  assert.match(styles, /\.selection-toolbar\{[^}]*gap:2px;[^}]*border-radius:18px/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.selection-toolbar\{[^}]*grid-template-columns:auto minmax\(58px,1fr\) auto auto auto/);
  assert.match(styles, /\.selection-toolbar-secondary\{display:contents\}/);
  assert.doesNotMatch(styles, /\.selection-toolbar\{[^}]*flex-wrap:wrap/);
  assert.equal((translations.match(/batchMoreActions:/g) || []).length, 3);
  assert.match(app, /app-command-dock[\s\S]*?<GenerationQueueDrawer[\s\S]*?className="floating-action-rail"/);
  assert.equal((app.match(/className="fab select-fab"/g) || []).length, 1);
  assert.match(app, /dataScopeMatches/);
  assert.match(app, /const \[viewTransition, setViewTransition\]/);
  assert.match(app, /startViewTransition\?: \(update: \(\) => void\) => NativeViewTransition/);
  assert.match(app, /transitionDocument\.startViewTransition\(\(\) => \{[\s\S]*?flushSync\(commitView\)/);
  assert.match(app, /className=\{`content-plane\$\{viewTransition/);
  assert.match(app, /const direction = nextView === 'explore' \? 'to-explore' : 'to-cards';/);
  assert.match(app, /window\.setTimeout\([\s\S]*?\}, 220\)/);
  assert.match(app, /loading && !dataScopeMatches \? ' is-scope-loading'/);
  assert.match(app, /const contentLoading = initialLoading[\s\S]*?clustersLoading/);
  assert.match(app, /loading=\{contentLoading\}/);
  assert.match(app, /className="error" role="alert"[\s\S]*?setItemsReloadKey\(key => key \+ 1\)/);
  assert.match(app, /hasActiveSearch=/);
  assert.match(app, /onOpenCollection=\{selectCluster\}/);
  assert.doesNotMatch(app, /ThumbnailBudget|THUMBNAIL_BUDGET/);
  assert.doesNotMatch(config, /range-setting|ThumbnailBudget|globalThumbnails|focusThumbnails/);
  assert.match(config, /\.config-button, \.toolbar-search input/);
  assert.doesNotMatch(styles, /constellation/);
  assert.match(explore, /onClick=\{\(\) => onOpen\(openItemId\)\}/);
  assert.match(explore, /onClick=\{\(\) => onOpenCollection\(cluster\)\}/);
  assert.doesNotMatch(explore, /focusedClusterId|onFocusCluster/);
  assert.doesNotMatch(cards, /mobile-masonry-columns|leftColumnItems|rightColumnItems/);
  assert.match(cards, /responsive-cards-grid/);
  assert.match(cards, /items\.length <= 8/);
  assert.match(styles, /\.card-image-frame img,[\s\S]*?height:auto;[\s\S]*?object-fit:contain/);
  assert.match(styles, /\.item-card:focus-within \.card-actions/);
  assert.match(styles, /\.card-open-hit:focus-visible\{[^}]*outline:2px/);
  assert.match(styles, /\.hover-action:focus-visible/);
  assert.match(styles, /\.item-card \.card-actions\{[^}]*display:flex!important;[^}]*width:max-content;[^}]*flex-direction:column;[^}]*align-items:flex-end;[^}]*opacity:1/);
  assert.match(styles, /\.item-card \.card-action-secondary\{display:none\}/);
  assert.match(styles, /\.item-card \.card-more-shell\{display:inline-flex;width:34px;height:34px\}/);
  assert.match(styles, /\.card-action-menu-item\{[\s\S]*?min-height:44px/);
  assert.match(itemCard, /className="card-action-menu" role="menu"/);
  assert.match(itemCard, /\['ArrowDown', 'ArrowUp', 'Home', 'End'\]/);
  assert.match(itemCard, /document\.addEventListener\('pointerdown', closeOutside\)/);
  assert.match(styles, /\.app-command-dock\{[\s\S]*?position:fixed/);
  assert.match(styles, /\.sr-only\{position:absolute;width:1px;height:1px/);
  assert.match(styles, /@media\(min-width:761px\) and \(max-width:900px\)/);
  assert.doesNotMatch(styles, /\.app-main\.is-refreshing[^\n]*filter:/);
  assert.match(styles, /--studio-accent:#a84532/);
  assert.match(styles, /html\[data-appearance="pine_archive"\]/);
  assert.match(styles, /html\[data-appearance="aubergine_ink"\]/);
  assert.match(styles, /html\{scrollbar-gutter:stable\}/);
  assert.match(styles, /\.chrome,\.app-main\{[\s\S]*?--ink:var\(--studio-ink\)/);
  assert.match(styles, /\.app-command-dock[\s\S]*?var\(--studio-ink\)/);
  assert.match(styles, /bottom:calc\(10px \+ env\(safe-area-inset-bottom\)\)/);
  assert.match(styles, /padding:10px calc\(14px \+ env\(safe-area-inset-right\)\) calc\(112px \+ env\(safe-area-inset-bottom\)\)/);
  assert.match(styles, /\.generation-count-menu\{[^}]*bottom:100%/);
  assert.match(styles, /\.generation-compose-card\.generation-composer-card\{height:auto;min-height:calc\(100dvh - 96px - env\(safe-area-inset-top\)\);overflow:visible;overscroll-behavior:auto\}/);
  assert.match(styles, /\.card-select-action\{[^}]*pointer-events:auto/);
  assert.doesNotMatch(styles, /\.generation-queue-row>span:first-of-type/);
  assert.match(styles, /@keyframes modal-panel-in\{from\{opacity:0;transform:translateY\(6px\)\}/);
  assert.doesNotMatch(styles, /studio-scope-in/);
  assert.match(styles, /\.generation-generating-block::after,.generation-shimmer,.content-loading-state span,.spin\{animation:none!important;transition:none!important\}/);
  assert.doesNotMatch(styles, /prefers-reduced-motion[\s\S]*?transform:none!important/);
  assert.match(styles, /\.generation-result-fade-in\{animation:none!important;transition:none!important;opacity:1!important\}/);
  assert.equal((translations.match(/cards: 'Library'/g) || []).length, 3);
  assert.match(toggle, /onView\('cards'\)/);
  assert.match(topBar, /className=\{`vista-button filter-button[\s\S]*?aria-label=\{t\('filters'\)\}/);
  assert.match(topBar, /className="logo-wordmark" lang="en"/);
  assert.match(topBar, /inert=\{modalOpen\} aria-hidden=\{modalOpen \|\| undefined\}/);
  assert.match(app, /const blockingModalOpen = !hasChosenUiLanguage \|\| Boolean\(detailId \|\| editorOpen \|\| standaloneGenerationOpen \|\| batchActionDialog\)/);
  assert.match(app, /allowDelete=\{showManagementActions\}/);
  assert.match(editorModal, /allowDelete && persistedItem/);
  assert.match(editorModal, /if \(!allowDelete \|\| !persistedItem \|\| deleting \|\| saving\) return;/);
  assert.match(generationPanel, /aria-labelledby="generation-workspace-title"/);
  assert.match(generationPanel, /window\.matchMedia\('\(prefers-reduced-motion: reduce\)'\)/);
  assert.match(queueDrawer, /const visibleSections = sections\.filter/);
  assert.match(queueDrawer, /inert=\{!open\}/);
  assert.match(queueDrawer, /aria-expanded=\{open\}/);
  assert.match(queueDrawer, /handleQueueKeyDown/);
  assert.match(queueDrawer, /className="generation-queue-scrim"[\s\S]*?closeDrawer\(\)/);
  assert.match(queueDrawer, /createPortal\(queueLayer, document\.body\)/);
  assert.match(queueDrawer, /refreshKey: number/);
  assert.doesNotMatch(queueDrawer, /document\.addEventListener\('pointerdown'/);
  assert.doesNotMatch(queueDrawer, /role=\{canOpenJob\(job\) \? 'button'/);
  assert.match(editorModal, /aria-labelledby="reference-editor-title"/);
  assert.match(suggestedTitleField, /data-modal-initial-focus/);
  assert.match(generationPanel, /data-modal-initial-focus/);
  assert.match(generationPanel, /handleModalKeyDown/);
  assert.match(generationPanel, /fullscreenCloseRef\.current/);
  assert.match(generationPanel, /fullscreenTriggerRef\.current/);
  assert.match(generationPanel, /role="dialog" aria-modal="true" aria-label=\{t\('recentGenerations'\)\}/);
  assert.match(generationPanel, /className=\{`generation-history-scrim/);
  assert.match(generationPanel, /className="generation-layout" inert=\{showHistoryDrawer\}/);
  assert.match(generationPanel, /className="generation-workspace-head" inert=\{showHistoryDrawer\}/);
  assert.match(itemCard, /if \(event\.key === 'Tab'\) \{[\s\S]*?setMoreOpen\(false\)/);
  assert.doesNotMatch(app, /const openProviders = \(\) => \{[^}]*setStandaloneGenerationOpen\(false\)/);
  assert.match(generationPanel, /referencePickerDialogRef/);
  assert.match(generationPanel, /libraryItemBackRef/);
  assert.match(generationPanel, /libraryItemRequestRef/);
  assert.match(generationPanel, /disabled=\{pickerBusy\}/);
  assert.match(generationPanel, /closeGenerationControl/);
  assert.match(modalFocus, /event\.stopPropagation\(\)/);
  assert.match(modalFocus, /isAvailableFocusTarget/);
  assert.match(modalFocus, /element === document\.body/);
  assert.match(modalFocus, /element\.getClientRects\(\)\.length > 0/);
  assert.match(modalFocus, /\.toolbar-search input/);
  assert.match(config, /focusFirstAvailable\(\[opener, \.\.\.fallbacks\]\)/);
  assert.match(config, /cleanupPrecheck/);
  assert.match(config, /const cleanupInFlightRef = useRef\(false\)/);
  assert.match(config, /if \(cleanupRequestRef\.current === requestId\)/);
  assert.match(config, /const providersRequestRef = useRef\(0\)/);
  assert.match(config, /const providerActionRequestRef = useRef\(0\)/);
  assert.match(config, /if \(providersRequestRef\.current !== requestId\) return;/);
  assert.match(config, /const closePanel = \(\) => \{[\s\S]*?providersRequestRef\.current \+= 1;[\s\S]*?providerActionRequestRef\.current \+= 1/);
  assert.match(config, /const pollCodexAuth = async \(\) => \{[\s\S]*?if \(providerActionRequestRef\.current !== requestId\) return;[\s\S]*?if \(providerActionRequestRef\.current === requestId\) setProviderBusy\(false\)/);
  assert.doesNotMatch(styles, /search-query-chip/);
  assert.match(styles, /\.item-card \.hover-action\{width:34px;height:34px;min-width:34px;min-height:34px/);
  assert.match(generationPanel, /\.generate-variant-button, \.mobile-generate-variant-button/);
  assert.match(generationPanel, /secondaryFallbackFocusSelector: item \? '\.detail\.modal'/);
  assert.match(modalFocus, /\.\.\.fallbacks, \.\.\.secondaryFallbacks, appFallback/);
  assert.match(appearance, /image-prompt-library\.appearance\.v1/);
  assert.match(appearance, /DEFAULT_APPEARANCE: AppearancePreset = 'gallery_vermilion'/);
  assert.match(app, /applyAppearance\(appearance\)/);
  for (const preset of ['gallery_vermilion', 'pine_archive', 'aubergine_ink']) {
    assert.match(config, new RegExp(preset));
  }
  const settingOrder = [
    "t('uiLanguage')",
    "t('promptCopyLanguage')",
    "t('appearance')",
    "t('appUpdate')",
    "t('cleanupTitle')",
    "t('providers')",
    "t('systemInformation')",
  ].map(marker => config.indexOf(marker));
  assert.ok(settingOrder.every(index => index >= 0));
  assert.deepEqual(settingOrder, [...settingOrder].sort((a, b) => a - b));
  assert.equal((config.match(/cfg\?\.library_path/g) || []).length, 1);
  assert.equal((config.match(/cfg\?\.database_path/g) || []).length, 1);
  assert.match(config, /filter\(provider => provider\.provider !== 'manual_upload'\)/);
  assert.match(generationPanel, /filter\(nextProvider => nextProvider\.provider !== 'manual_upload'\)/);
  assert.match(generationPanel, /\.catch\(\(\) => \{\s*if \(cancelled\) return;\s*setProviders/);
  assert.match(queueDrawer, /api\.generationSet\(group\.generationGroupId\)/);
  assert.match(queueDrawer, /queueLoadOlder/);
  assert.doesNotMatch(queueDrawer, /\.slice\(0,\s*8\)/);
  assert.match(queueDrawer, /const refreshRequestRef = useRef\(0\)/);
  assert.match(queueDrawer, /if \(refreshRequestRef\.current !== requestId\) return;/);
  assert.match(queueDrawer, /const openSetRequestRef = useRef\(0\)/);
  assert.match(queueDrawer, /if \(openSetRequestRef\.current !== requestId\) return;/);
  assert.match(queueDrawer, /useEffect\(\(\) => \(\) => \{[\s\S]*?openSetRequestRef\.current \+= 1/);
  assert.match(queueDrawer, /cancelGenerationJob\(job\.id\)[\s\S]*?await refresh\(\)/);
  assert.match(queueDrawer, /loading="lazy" decoding="async"/);
  assert.match(app, /const showFloatingActions = Boolean\(hasChosenUiLanguage/);
  assert.match(app, /const generationJobRequestRef = useRef\(0\)/);
  assert.match(app, /if \(generationJobRequestRef\.current !== requestId\) return;/);
  assert.match(app, /const clustersRequestRef = useRef\(0\)/);
  assert.match(app, /const libraryTotalRequestRef = useRef\(0\)/);
  assert.match(app, /if \(libraryTotalRequestRef\.current === requestId\) setLibraryTotal/);
  assert.match(app, /const \[generationQueueRefreshKey, setGenerationQueueRefreshKey\]/);
  assert.match(app, /const batchActionInFlightRef = useRef\(false\)/);
  assert.match(app, /if \(!selectedItemIds\.size \|\| batchActionInFlightRef\.current\) return false;/);
  assert.match(app, /const cancelPendingEdit = \(\) => \{/);
  assert.match(app, /const openGenerationQueue = \(\) => \{[\s\S]*?cancelPendingEdit\(\)/);
  assert.match(app, /if \(result\.failed > 0\)/);
  assert.match(editorModal, /t\('savePartiallyCompleted'\)/);
  assert.match(editorModal, /await api\.deleteItem\(saved\.id\)/);
  assert.match(editorModal, /resultUploaded && reconciled\?\.images\.some\(image => image\.role === 'result_image'\)/);
  assert.match(generationPanel, /const generationSetRequestRef = useRef\(0\)/);
  assert.match(generationPanel, /if \(generationSetRequestRef\.current !== requestId\) return undefined;/);
  assert.match(generationPanel, /localizedGenerationSetProgressText\(activeGenerationSet, t\)/);
  assert.match(generationPanel, /if \(busy && !force\) return;/);
  assert.match(generationPanel, /handleClose\(true\)/);
  assert.match(generationPanel, /handleReferenceSourceMenuKeyDown/);
  assert.match(generationPanel, /\['ArrowDown', 'ArrowUp', 'Home', 'End'\]/);
  assert.match(generationPanel, /saveAsNewDialogRef/);
  assert.match(generationPanel, /queueQueuedCancelNote/);
  assert.doesNotMatch(styles, /--card-min/);
  assert.doesNotMatch(styles, /\.tabs \.active/);
  assert.doesNotMatch(styles, /^\.prompt-panel\{/m);
});

test('Explore detail boundary keeps local mutation actions while gating management controls', async () => {
  const [app, detail] = await Promise.all([
    readFile(`${ROOT}/frontend/src/App.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ItemDetailModal.tsx`, 'utf8'),
  ]);

  assert.match(app, /const showManagementActions = !isDemoMode && view === 'cards';/);
  assert.match(app, /showMutations={!isDemoMode} showManagementActions={showManagementActions}/);
  assert.match(detail, /const allowManagementActions = showMutations && showManagementActions;/);
  assert.match(detail, /const inlineMutationBusyRef = useRef\(false\)/);
  assert.match(detail, /if \(!item \|\| inlineMutationBusyRef\.current\) return;/);
  assert.match(detail, /disabled=\{deleteBusy\}/);
  assert.match(detail, /showMutations && canGenerate/);
  assert.match(detail, /showMutations && <button className="modal-icon-button edit-button"/);
  assert.match(detail, /allowManagementActions && <button className="modal-icon-button favorite-button"/);
  assert.match(detail, /allowManagementActions && <button className="modal-icon-button detail-delete-button"/);
  assert.match(detail, /allowManagementActions && editingPromptLanguage === lang/);
  assert.match(detail, /allowManagementActions && \(addingTag \?/);
  assert.match(detail, /selectedImage \|\| showMutations/);
  assert.match(detail, /className="modal-icon-button detail-fullscreen-overlay"/);
  assert.doesNotMatch(detail, /heroAspectRatio/);
  assert.match(detail, /focusFirstAvailable\(\[opener, \.\.\.fallbacks, searchFallback\]\)/);
  assert.match(detail, /\[data-card-id\]/);
  assert.equal((detail.match(/\{selectedImage && <a className="modal-icon-button download-button"/g) || []).length, 2);
  assert.match(detail, /mobile-generate-variant-button"[\s\S]*?aria-label=\{t\('generateVariant'\)\}[\s\S]*?mobile-generate-variant-label">\{t\('generate'\)\}/);
  assert.match(detail, /generate-variant-button"[\s\S]*?aria-label=\{t\('generateVariant'\)\}[\s\S]*?>\{t\('generate'\)\}<\/button>/);
});

test('batch review closure keeps save, provenance, references, and mobile actions compact', async () => {
  const [generation, itemCard, styles] = await Promise.all([
    readFile(`${ROOT}/frontend/src/components/GenerationPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ItemCard.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/styles.css`, 'utf8'),
  ]);

  assert.match(generation, /if \(readOnly && attachments\.length === 0\) return null;/);
  assert.match(generation, /generation-history-prompt-preview\$\{jobAttachments\(historyReviewJob\)\.length \? ' has-references' : ''\}/);
  assert.match(generation, /className="generation-history-prompt-primary-actions"/);
  assert.match(generation, /className=\{`generation-save-view\$\{isSavePanelClosing/);
  assert.match(generation, /generation-locked-record[\s\S]*?t\('providers'\)[\s\S]*?t\('queueModel'\)[\s\S]*?t\('originalItem'\)[\s\S]*?t\('batchPosition'\)/);
  assert.match(generation, /onAcceptedRef\.current\(undefined, t\('newVariantCreated'\)\)/);
  assert.match(generation, /t\('saveAndContinue'\)/);
  assert.match(generation, /t\('continueReview'\)\.replace\('\$\{count\}'/);
  assert.match(generation, /const preservePausedReview = Boolean\(batchReviewSession && batchReviewPaused\)/);
  assert.match(generation, /reconcileGenerationReviewSession\(batchReviewSession, jobs\)/);
  assert.match(generation, /const invalidateGenerationRefreshRequests = \(\) => \{[\s\S]*?jobsRequestRef\.current \+= 1;[\s\S]*?generationSetRequestRef\.current \+= 1;/);
  assert.match(generation, /const jobsRef = useRef<GenerationJobRecord\[\]>\(jobs\)/);
  assert.match(generation, /const nextJobs = updateGenerationJobs\(current => current\.map/);
  assert.match(generation, /const fetchedJob = await api\.generationJob\(initialJobId\)/);
  assert.match(generation, /if \(options\.preserveActive\)[\s\S]*?preservedIds[\s\S]*?mergeGenerationJobs\(preservedJobs, nextJobs\)/);
  assert.match(generation, /const batchReviewCursorJobIdRef = useRef<string \| undefined>\(initialJobId\)/);
  assert.match(generation, /const nextReady = generationReviewNext\(jobs, batchReviewSession, batchReviewCursorJobIdRef\.current\)/);
  assert.match(generation, /const reviewSession = ensureBatchReviewSession\(job\);[\s\S]*?api\.cancelGenerationJob\(job\.id\)[\s\S]*?const resolvedSession = resolveGenerationReviewSlot\(reviewSession, updated, 'cancelled'\)[\s\S]*?advanceBatchReview\(updated, resolvedSession, nextJobs\)/);
  assert.match(generation, /const fetchedRetryJob = await api\.generationJob\(retryId\)/);
  assert.match(generation, /t\(language\.labelKey\)\.replace\(\/ prompt\$\/i, ''\)/);
  assert.doesNotMatch(generation, /save-new-metadata-panel|readonly-provenance/);
  assert.doesNotMatch(generation, /<dd>\{reviewJob\.(?:id|source_item_id|provider)\}<\/dd>/);

  assert.match(itemCard, /card-action-copy/);
  assert.match(itemCard, /card-action-more/);
  assert.match(itemCard, /className="card-action-menu" role="menu"/);
  assert.match(itemCard, /document\.addEventListener\('pointerdown', closeOutside\)/);
  assert.match(itemCard, /document\.addEventListener\('keydown', closeOnEscape\)/);
  assert.match(itemCard, /setMoreOpen\(false\);[\s\S]*?onFavorite/);
  assert.match(itemCard, /setMoreOpen\(false\);[\s\S]*?onEdit/);

  assert.match(styles, /\.generation-save-view \.save-new-metadata-grid\{[\s\S]*?grid-template-columns:minmax\(320px,\.9fr\) minmax\(420px,1\.1fr\)[\s\S]*?overflow:hidden/);
  assert.match(styles, /\.generation-save-view \.save-new-fields\{[\s\S]*?overflow-y:auto/);
  assert.match(styles, /@media\(min-width:761px\) and \(max-width:900px\)\{[\s\S]*?grid-template-columns:minmax\(240px,\.8fr\) minmax\(0,1\.2fr\)/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.generation-save-view \.save-new-metadata-grid\{grid-template-columns:minmax\(0,1fr\);grid-template-rows:minmax\(140px,30dvh\) minmax\(0,1fr\)/);
  assert.match(styles, /\.item-card \.card-action-secondary\{display:none\}/);
  assert.match(styles, /\.item-card \.card-more-shell\{display:inline-flex;width:34px;height:34px\}/);
  assert.match(styles, /\.card-more-shell\{position:relative;display:none\}/);
  assert.match(styles, /\.generation-history-prompt-preview\{[^}]*grid-template-rows:minmax\(180px,1fr\) auto;[^}]*gap:12px/);
  assert.match(styles, /\.generation-history-prompt-preview\.has-references\{grid-template-rows:minmax\(180px,1fr\) auto auto\}/);
  assert.match(styles, /\.generation-history-prompt-actions button\{[^}]*height:44px;[^}]*min-height:44px;[^}]*border-radius:10px/);
  assert.match(styles, /\.generation-queue-quick-expand,\.generation-queue-quick-discard\{[^}]*width:44px;[^}]*height:44px/);
  assert.match(styles, /\.generation-download-overlay,\.generation-fullscreen-overlay\{position:absolute/);
  assert.match(styles, /\.generation-fullscreen-close,\.detail-fullscreen-close\{display:none;position:fixed/);
  assert.match(styles, /\.detail\.modal \.detail-side-actions \.modal-icon-button,\s*\.detail\.modal \.detail-side-actions > \.close\{[^}]*position:relative;[^}]*top:auto;[^}]*right:auto/);
  assert.match(styles, /\.generation-stage-result \.generation-fullscreen-close\{[^}]*width:44px;[^}]*height:44px/);
  assert.match(styles, /@media\(max-width:420px\)\{[\s\S]*?\.generation-history-prompt-actions\{display:grid;grid-template-columns:minmax\(0,1fr\);gap:8px\}[\s\S]*?\.generation-history-prompt-primary-actions\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\);width:100%;gap:8px\}/);
});

test('redesign interaction guards keep overlays mutually exclusive and focus-safe', async () => {
  const [app, filters, config, detail, generation, focus, styles] = await Promise.all([
    readFile(`${ROOT}/frontend/src/App.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/FiltersPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ConfigPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ItemDetailModal.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/GenerationPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/hooks/useModalFocus.ts`, 'utf8'),
    readFile(`${ROOT}/frontend/src/styles.css`, 'utf8'),
  ]);

  assert.match(app, /setGenerationQueueOpen\(false\); setFiltersOpen\(true\)/);
  assert.match(app, /setGenerationQueueOpen\(false\); setConfigOpen\(true\)/);
  assert.match(app, /const openGenerationFromDetail = \(item: ItemDetail\) => \{[\s\S]*?setGenerationSourceItem\(item\);[\s\S]*?setStandaloneGenerationOpen\(true\)/);
  assert.match(app, /const closeStandaloneGeneration = \(\) => \{[\s\S]*?setStandaloneGenerationOpen\(false\);[\s\S]*?setGenerationSourceItem\(undefined\);[\s\S]*?\};/);
  assert.match(app, /\{!standaloneGenerationOpen && detailId && <ItemDetailModal key=\{detailId\}/);
  assert.match(app, /\{standaloneGenerationOpen && <GenerationPanel item=\{generationSourceItem\}/);
  assert.match(app, /className="app-content" inert=\{drawerModalOpen\}/);
  assert.match(filters, /const selectCluster = \(cluster: ClusterRecord\) => \{[\s\S]*closePanel\(\);[\s\S]*onSelect\(cluster\)/);
  assert.match(filters, /const clearSelection = \(\) => \{[\s\S]*closePanel\(\);[\s\S]*onClear\(\)/);
  assert.match(filters, /window\.requestAnimationFrame\(\(\) => \{[\s\S]*?focusTarget\?\.focus/);
  assert.match(config, /window\.requestAnimationFrame\(\(\) => \{[\s\S]*?closeButtonRef\.current\?\.focus/);
  assert.match(filters, /className="drawer-scrim"[\s\S]*?onClick=\{closePanel\}/);
  assert.match(config, /className="drawer-scrim"[\s\S]*?onClick=\{closePanel\}/);
  assert.doesNotMatch(config, />verification_url<|user_code:\s*\{/);
  assert.doesNotMatch(config, /This app is running from Terminal/);
  assert.match(generation, /pendingAcceptedRef/);
  assert.match(generation, /generationFailure\(selectedStageJob, t\)/);
  assert.match(generation, /generation-history-drawer open/);
  assert.match(generation, /historyTriggerRef\.current\?\.focus/);
  assert.doesNotMatch(generation, /setGenerationCountMenuOpen\(open => !open\)/);
  assert.match(generation, /if \(generationCountMenuOpen\) \{[\s\S]*?\[role="menuitem"\][\s\S]*?return;[\s\S]*?setGenerationCountMenuOpen\(true\);/);
  assert.doesNotMatch(generation, /Could not (?:create|run|accept|read|load|save|cancel|discard|retry|mark)/);
  assert.doesNotMatch(detail, /aria-label="(?:Confirm|Cancel) edit"/);
  assert.doesNotMatch(detail, /import GenerationPanel|<GenerationPanel/);
  assert.match(focus, /hasActiveModalOutside\([\s\S]*?restoreCandidates/);
  assert.match(focus, /dialog\.contains\(candidate\)/);
  assert.match(styles, /\.card-actions\{[\s\S]*?position:absolute;[\s\S]*?display:flex;[\s\S]*?width:max-content/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.item-card \.card-actions\{[^}]*display:flex!important;[^}]*width:max-content;[^}]*opacity:1;[^}]*transform:none;[^}]*pointer-events:auto/);
  assert.match(styles, /@media \(min-width:761px\) and \(hover:none\),\(min-width:761px\) and \(pointer:coarse\)\{[\s\S]*?\.item-card \.card-actions\{display:flex;width:max-content;opacity:1;transform:none;pointer-events:auto/);
  assert.match(styles, /@media\(max-width:400px\)\{[\s\S]*?\.responsive-cards-grid\{column-count:1\}/);
  assert.match(styles, /@media\(max-width:400px\)\{[\s\S]*?\.responsive-cards-grid\.is-sparse\.sparse-count-2\{grid-template-columns:1fr;gap:18px\}/);
  assert.match(styles, /\.hover-action\{[\s\S]*?cursor:pointer;/);
  assert.match(styles, /\.card-media\{position:relative;z-index:2;pointer-events:none\}/);
  assert.doesNotMatch(styles, /\.item-card\.is-selecting \.card-actions/);
  assert.match(styles, /\.drawer-scrim\{[\s\S]*?position:fixed;[\s\S]*?z-index:119/);
  assert.match(styles, /\.generation-queue-scrim\{[\s\S]*?position:fixed;[\s\S]*?z-index:59/);
  assert.match(styles, /\.detail\.modal\{[\s\S]*?height:min\(760px,calc\(100dvh - 32px\)\)[\s\S]*?overflow:hidden/);
  assert.match(styles, /\.detail-layout\{[\s\S]*?grid-template-columns:minmax\(0,1fr\) clamp\(400px,32vw,440px\)/);
  assert.match(styles, /\.detail-fullscreen-overlay\{position:absolute;right:12px;top:20px/);
  assert.match(styles, /\.modal-hero \.detail-fullscreen-frame\{[^}]*position:absolute;[^}]*inset:0;[^}]*width:100%;[^}]*height:100%/);
  assert.match(styles, /\.mobile-hero-actions\{position:absolute;inset:0;[^}]*pointer-events:none/);
  assert.match(styles, /\.mobile-generate-variant-button\{display:inline-flex;[^}]*width:auto/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.detail-side-actions\{display:none\}/);
  assert.match(detail, /--detail-image-aspect-ratio/);
  assert.match(detail, /heroFullscreenCloseRef\.current/);
  assert.match(detail, /heroFullscreenTriggerRef\.current/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.modal-hero\{height:auto;min-height:260px;max-height:min\(72dvh,680px\);aspect-ratio:var\(--detail-image-aspect-ratio,4 \/ 3\)/);
  assert.match(styles, /\.modal-hero\.is-mobile-fullscreen\{height:100dvh;min-height:100dvh;max-height:none;aspect-ratio:auto\}/);
  assert.match(styles, /\.scope-sort-control\{[\s\S]*?cursor:pointer/);
  assert.match(styles, /\.scope-sort-picker\{position:relative;display:flex;align-items:center;min-width:0\}/);
  assert.match(styles, /\.scope-sort-select\{[^}]*width:auto;[^}]*cursor:pointer;[^}]*appearance:none/);
  assert.doesNotMatch(styles, /\.scope-sort-select\{[^}]*position:absolute;[^}]*opacity:0/);
  assert.match(styles, /main\{max-width:1600px[\s\S]*?@media\(min-width:1760px\)\{main,\.chrome \.nav-row,\.status-row\{max-width:1920px\}\}/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.view-dock\{grid-column:1\/-1;grid-row:3;justify-self:stretch;width:100%;margin-top:1px\}[\s\S]*?\.view-dock \.toggle\{width:100%;height:44px;gap:0;padding:0;border:0;overflow:hidden\}[\s\S]*?\.view-dock \.toggle button\{flex:1 1 50%;min-height:44px;padding:0 13px;border-radius:0\}/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.scope-sort-control\{height:40px;max-width:min\(190px,48vw\);min-height:40px\}[\s\S]*?\.scope-sort-select\{height:38px;min-height:38px/);
  assert.match(styles, /\.generation-generating-block::after\{[\s\S]*?opacity:0[\s\S]*?transform:translateX\(-130%\)[\s\S]*?animation:generation-exposure-sweep 1\.45s/);
  assert.match(styles, /@keyframes generation-exposure-sweep/);
  assert.match(styles, /\.generation-download-overlay,\.generation-fullscreen-overlay\{[^}]*position:absolute;[^}]*top:12px;[^}]*z-index:9/);
  assert.match(styles, /\.content-plane\{min-width:0\}/);
  assert.match(styles, /html\[data-view-transition\]\{view-transition-name:none\}/);
  assert.match(styles, /html\[data-view-transition\] \.content-plane\{view-transition-name:library-content\}/);
  assert.match(styles, /html\[data-view-transition\] \.chrome\{view-transition-name:library-chrome\}/);
  assert.match(styles, /html\[data-view-transition\] \.app-command-dock\{view-transition-name:library-command-dock\}/);
  assert.match(styles, /::view-transition-group\(library-content\),[\s\S]*?::view-transition-new\(library-command-dock\)\{animation:none\}/);
  assert.match(styles, /\.content-plane\.to-explore\{animation:content-plane-from-left 220ms/);
  assert.match(styles, /\.content-plane\.to-cards\{animation:content-plane-from-right 220ms/);
  assert.match(styles, /html\[data-view-transition="to-explore"\]::view-transition-old\(library-content\)/);
  assert.match(styles, /html\[data-view-transition="to-cards"\]::view-transition-new\(library-content\)/);
  assert.match(styles, /button,input,textarea,select\{font:inherit\}/);
  assert.match(styles, /@font-face\{\s*font-family:"IPL YaHei Balanced";\s*src:local\("Microsoft YaHei UI Light"\),local\("Microsoft YaHei Light"\);\s*font-style:normal;\s*font-weight:100 500/);
  assert.match(styles, /@font-face\{\s*font-family:"IPL YaHei Balanced";\s*src:local\("Microsoft YaHei UI"\),local\("Microsoft YaHei"\);\s*font-style:normal;\s*font-weight:501 900/);
  assert.match(styles, /--font-ui-zh-hans:"IPL YaHei Balanced","Microsoft YaHei UI","Microsoft YaHei"/);
  assert.match(styles, /html:lang\(zh-Hant\) \.scope-heading h1,[\s\S]*?font-weight:700/);
  assert.match(styles, /\.inline-edit-confirm,.inline-edit-cancel\{[\s\S]*?border-radius:10px/);
  assert.match(styles, /\.copy-toast\.elegant-toast\.is-closing/);
  assert.match(detail, /<div className="detail-modal-content">/);
  assert.doesNotMatch(detail, /modal-content-enter/);
  assert.match(generation, /\{\(!selectedStageJob \|\| !jobResultUrl\(selectedStageJob\)\) && renderSiblingNavigation\(\)\}/);
  assert.match(generation, /className="generation-sibling-previous"/);
  assert.match(generation, /className="generation-sibling-next"/);
  assert.match(generation, /const openLibraryPicker = async \(\) => \{[\s\S]*?const requestId = \+\+libraryItemRequestRef\.current;[\s\S]*?if \(requestId === libraryItemRequestRef\.current\) \{[\s\S]*?setLibraryItems/);
  assert.match(generation, /const openRecentPicker = async \(\) => \{[\s\S]*?const requestId = \+\+libraryItemRequestRef\.current;[\s\S]*?if \(requestId === libraryItemRequestRef\.current\) \{[\s\S]*?setRecentJobs/);
  assert.match(focus, /element\.hasAttribute\('disabled'\)/);
  assert.match(focus, /element\.getAttribute\('aria-disabled'\) === 'true'/);
  assert.match(styles, /\.generation-sibling-navigation\{position:absolute;inset:0/);
  assert.match(styles, /\.generation-sibling-navigation button\{[^}]*width:44px;[^}]*height:44px;[^}]*border:0;[^}]*background:transparent;[^}]*box-shadow:none;[^}]*backdrop-filter:none/);
  assert.match(styles, /\.generation-sibling-navigation button:disabled\{[^}]*visibility:hidden;[^}]*pointer-events:none/);
  assert.match(styles, /\.generation-sibling-count\{[^}]*border:1px solid var\(--studio-glass-border\);[^}]*background:var\(--studio-glass-fill\);[^}]*box-shadow:var\(--studio-glass-shadow-compact\)/);
  assert.match(styles, /\.generation-sibling-previous\{left:12px\}/);
  assert.match(styles, /\.generation-sibling-next\{right:12px\}/);
  assert.doesNotMatch(styles, /\.scope-sort-control>span/);
  assert.doesNotMatch(styles, /\.card-template-badge\{font-size:11px\}/);
});

test('Explore/detail CSS keeps responsive grids, token controls, CJK hierarchy, and fullscreen motion', async () => {
  const styles = await readFile(`${ROOT}/frontend/src/styles.css`, 'utf8');
  const previewImgRule = styles.match(/\.explore-collection-preview img\{([^}]*)\}/)?.[1] || '';

  assert.match(styles, /\.explore-collection-grid\{display:grid;grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.explore-collection-grid\{grid-template-columns:1fr;gap:12px\}/);
  assert.match(previewImgRule, /(?:^|;)width:auto;/);
  assert.match(previewImgRule, /(?:^|;)max-width:100%;/);
  assert.match(previewImgRule, /(?:^|;)margin-inline:auto(?:;|$)/);
  assert.doesNotMatch(previewImgRule, /(?:^|;)width:100%;/);
  assert.match(styles, /\.detail-side-actions\{[^}]*min-height:44px/);
  assert.match(styles, /\.generation-queue-quick-expand,[\s\S]*?\.generation-stage-result \.stage-action\{[\s\S]*?width:44px;[\s\S]*?min-width:44px;[\s\S]*?height:44px;[\s\S]*?min-height:44px/);
  assert.doesNotMatch(styles, /\.hover-action::before/);
  assert.doesNotMatch(styles, /\.detail\.modal \.detail-side-actions \.modal-icon-button::before/);
  assert.doesNotMatch(styles, /\.detail\.modal \.modal-hero \.modal-icon-button::before/);
  assert.match(styles, /\.hover-action\{[\s\S]*?border:0;[\s\S]*?border-radius:999px;[\s\S]*?color:var\(--studio-ink\);[\s\S]*?background:rgb\(var\(--studio-surface-rgb\) \/ \.94\);[\s\S]*?box-shadow:0 8px 18px rgb\(var\(--studio-ink-rgb\) \/ \.18\)/);
  assert.match(styles, /\.hover-action:hover,\.hover-action:focus-visible\{[^}]*color:var\(--studio-ink\);[^}]*background:rgb\(var\(--studio-surface-rgb\) \/ \.98\);[^}]*outline:0/);
  assert.match(styles, /\.hover-action:focus-visible\{[^}]*box-shadow:0 0 0 2px var\(--accent-strong\),0 10px 22px rgb\(var\(--studio-ink-rgb\) \/ \.2\)/);
  assert.match(styles, /\.detail\.modal \.generate-variant-button\{[\s\S]*?height:44px;[\s\S]*?min-height:44px;[\s\S]*?border-radius:10px[\s\S]*?flex:0 0 auto;[\s\S]*?background:var\(--studio-accent-soft\)[\s\S]*?white-space:nowrap/);
  assert.match(styles, /--studio-glass-filter:saturate\(1\.16\) blur\(14px\)/);
  assert.match(styles, /--studio-glass-fill:var\(--studio-surface\);[\s\S]*?--studio-glass-fill-strong:var\(--studio-surface\);[\s\S]*?--studio-glass-dark-fill:rgb\(16 16 18\)/);
  assert.match(styles, /\.generation-queue-quick-expand,[\s\S]*?\.generation-stage-result \.stage-action\{[\s\S]*?background:var\(--studio-glass-fill\);[\s\S]*?box-shadow:var\(--studio-glass-shadow-compact\)/);
  assert.match(styles, /\.scope-sort-control:focus-within\{[^}]*background:rgb\(var\(--studio-accent-rgb\) \/ \.06\);outline:0/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.item-card \.hover-action\{[^}]*background:rgb\(var\(--studio-surface-rgb\) \/ \.92\)/);
  assert.match(styles, /html:lang\(zh-Hant\) \.detail\.modal \.generate-variant-button,[\s\S]*?width:44px;[\s\S]*?min-width:44px;[\s\S]*?flex-basis:44px/);
  assert.match(styles, /@supports \(\(-webkit-backdrop-filter:blur\(1px\)\) or \(backdrop-filter:blur\(1px\)\)\)\{[\s\S]*?\.item-card \.hover-action\{[\s\S]*?backdrop-filter:var\(--studio-glass-filter\)/);
  assert.match(styles, /\.generation-stage-result \.stage-action:disabled\{opacity:\.45;cursor:not-allowed\}/);
  assert.doesNotMatch(styles, /(?:^|\n)\.stage-action\{[^}]*background:var\(--studio-glass-fill\)/);
  assert.match(styles, /@supports \(\(-webkit-backdrop-filter:blur\(1px\)\) or \(backdrop-filter:blur\(1px\)\)\)\{[\s\S]*?\.app-command-dock,[\s\S]*?backdrop-filter:var\(--studio-glass-filter\)/);
  assert.match(styles, /@media\(prefers-reduced-transparency:reduce\)\{[\s\S]*?--studio-glass-fill:var\(--studio-surface\)[\s\S]*?--studio-glass-dark-fill:rgb\(16 16 18\)[\s\S]*?backdrop-filter:none!important/);
  assert.match(styles, /\.detail\.modal \.modal-hero \.mobile-generate-variant-button\{[^}]*width:auto;[^}]*white-space:nowrap/);
  assert.doesNotMatch(styles, /\.modal-icon-button\.mobile-hero-close\{[^}]*background:rgba\(41,36,38/);
  assert.match(styles, /\.detail\.modal \.detail-side-actions \.detail-delete-button\{\s*color:var\(--studio-ink\)/);
  assert.match(styles, /\.detail\.modal \.detail-side-actions \.detail-delete-button:hover,[\s\S]*?background:#f7e5e1[\s\S]*?color:#84382f/);
  assert.match(styles, /@keyframes detail-fullscreen-enter\{from\{opacity:0;transform:scale\(\.985\)\}to\{opacity:1;transform:scale\(1\)\}\}/);
  assert.match(styles, /\.detail\.modal \.detail-fullscreen-frame:fullscreen \.hero-image,[\s\S]*?animation:detail-fullscreen-enter 170ms/);
  assert.match(styles, /@media\(prefers-reduced-motion:reduce\)[\s\S]*?\.detail\.modal \.detail-fullscreen-frame:fullscreen \.hero-image,[\s\S]*?animation:none!important/);
  assert.match(styles, /\.filter-button\{[^}]*font-size:14px;[^}]*font-weight:700/);
  assert.match(styles, /\.logo\{[^}]*user-select:none/);
  assert.match(styles, /\.local-setup-list div\{[^}]*grid-template-columns:minmax\(0,1fr\)/);
  assert.match(styles, /html:lang\(zh-Hant\) \.toggle button,[\s\S]*?font-weight:400/);
  assert.match(styles, /html:lang\(zh-Hant\) \.filter-button\.active,[\s\S]*?font-weight:700/);
  assert.match(styles, /html:lang\(zh-Hant\) \.filter-drawer \.filter-pill-grid button,[\s\S]*?font-weight:400/);
  assert.match(styles, /html:lang\(zh-Hant\) \.filter-drawer \.filter-pill-grid button\.selected,[\s\S]*?font-weight:700/);
  assert.match(styles, /\.app-command-dock \.floating-action-rail \.fab\{[^}]*font-size:14px;[^}]*font-weight:700/);
  assert.match(styles, /@media\(max-width:760px\)\{[\s\S]*?\.app-command-dock \.floating-action-rail \.fab\{[^}]*font-size:14px/);
  assert.match(styles, /@media\(max-width:340px\)\{[\s\S]*?\.app-command-dock \.floating-action-rail \.fab\{padding:0 5px;font-size:14px\}/);
  assert.match(styles, /html:lang\(zh-Hant\) \.app-command-dock \.fab,[\s\S]*?font-weight:700/);
  assert.match(styles, /@media\(prefers-reduced-motion:reduce\)\{[\s\S]*?\.generation-sibling-navigation button\{transition:none!important\}[\s\S]*?transform:translateY\(-50%\)/);
  assert.doesNotMatch(styles, /html:lang\(zh-Hant\) \.metadata-inline-edit/);
});

test('title suggestions are explicit, prompt-only, and shared by both save flows', async () => {
  const [field, client, editor, generation] = await Promise.all([
    readFile(`${ROOT}/frontend/src/components/SuggestedTitleField.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/api/client.ts`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ItemEditorModal.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/GenerationPanel.tsx`, 'utf8'),
  ]);

  assert.match(field, /api\.suggestTitle\(\{ prompt_text: requestedPrompt \}\)/);
  assert.match(field, /setSuggestion\(result\.title\)/);
  assert.match(field, /onClick=\{\(\) => \{ onChange\(suggestion\); setSuggestion\(''\); \}\}/);
  assert.doesNotMatch(field, /onChange\(result\.title\)/);
  assert.match(client, /suggestTitle: \(_payload: TitleSuggestionRequest\) => demoReadOnly\(\)/);
  assert.match(client, /openai-codex-native\/suggest-title/);
  assert.match(editor, /<SuggestedTitleField[^>]*promptText=\{titleSuggestionPrompt\}/);
  assert.match(generation, /<SuggestedTitleField[^>]*promptText=\{metadataDraft\.prompts\?\.\[0\]\?\.text \|\| ''\}/);
});
