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
    onFocusCluster: () => undefined,
    onClearCluster: () => undefined,
    onOpen: () => undefined,
    onCopyPrompt: () => undefined,
    ...props,
  }));
}

before(async () => {
  vite = await createServer({
    root: FRONTEND_ROOT,
    configFile: fileURLToPath(new URL('../vite.config.ts', import.meta.url)),
    appType: 'custom',
    server: { middlewareMode: true },
  });
  ({ default: ExploreView } = await vite.ssrLoadModule('/src/components/ExploreView.tsx'));
});

after(async () => {
  await vite?.close();
});

test('Explore directory lists only non-empty Collections with uncropped preview metadata', () => {
  const activeCluster = { id: 'active', name: 'Portraits', count: 60, preview_images: ['media/item-0.webp', 'media/item-1.webp', 'media/item-2.webp'] };
  const emptyCluster = { id: 'empty', name: 'Empty Collection', count: 0, preview_images: [] };
  const items = Array.from({ length: 60 }, (_, index) => item(index, activeCluster));
  const html = render({ clusters: [activeCluster, emptyCluster], items, total: 60 });

  assert.match(html, /class="explore-directory"/);
  assert.match(html, /Portraits/);
  assert.doesNotMatch(html, /Empty Collection/);
  assert.equal((html.match(/class="explore-collection-preview"/g) || []).length, 3);
  assert.match(html, /width="900" height="600"/);
  assert.doesNotMatch(html, /constellation/);
});

test('Explore feed renders the first 48 natural-ratio cards and keeps management actions out', () => {
  const cluster = { id: 'active', name: 'Portraits', count: 60, preview_images: [] };
  const items = Array.from({ length: 60 }, (_, index) => item(index, cluster));
  const html = render({ clusters: [cluster], items, total: 60, focusedClusterId: cluster.id });

  assert.match(html, /class="explore-feed"/);
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
  assert.match(searchHtml, /No matching prompts/);

  const unclusteredHtml = render({ items: [item(0)], total: 1 });
  assert.match(unclusteredHtml, /No collections found/);
  assert.doesNotMatch(unclusteredHtml, /Your library is empty/);
});

test('Explore wiring preserves internal cards compatibility and removes constellation controls', async () => {
  const [app, config, styles, translations, toggle] = await Promise.all([
    readFile(`${ROOT}/frontend/src/App.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ConfigPanel.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/styles.css`, 'utf8'),
    readFile(`${ROOT}/frontend/src/utils/i18n.ts`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ViewToggle.tsx`, 'utf8'),
  ]);

  assert.match(app, /nextView !== 'cards'/);
  assert.match(app, /view === 'cards' && selectionMode/);
  assert.match(app, /dataScopeMatches/);
  assert.match(app, /hasActiveSearch=/);
  assert.doesNotMatch(app, /ThumbnailBudget|THUMBNAIL_BUDGET/);
  assert.doesNotMatch(config, /range-setting|ThumbnailBudget|globalThumbnails|focusThumbnails/);
  assert.doesNotMatch(styles, /constellation/);
  assert.match(styles, /\.explore-masonry \.card-image-frame img\{[^}]*height:auto;[^}]*object-fit:contain/);
  assert.match(styles, /\.explore-masonry \.card-image-frame\.natural-ratio img\{min-height:0\}/);
  assert.equal((translations.match(/cards: 'Library'/g) || []).length, 3);
  assert.match(toggle, /onView\('cards'\)/);
});

test('Explore detail boundary keeps local mutation actions while gating management controls', async () => {
  const [app, detail] = await Promise.all([
    readFile(`${ROOT}/frontend/src/App.tsx`, 'utf8'),
    readFile(`${ROOT}/frontend/src/components/ItemDetailModal.tsx`, 'utf8'),
  ]);

  assert.match(app, /const showManagementActions = !isDemoMode && view === 'cards';/);
  assert.match(app, /showMutations={!isDemoMode} showManagementActions={showManagementActions}/);
  assert.match(detail, /const allowManagementActions = showMutations && showManagementActions;/);
  assert.match(detail, /showMutations && canGenerate/);
  assert.match(detail, /showMutations && <button className="modal-icon-button edit-button"/);
  assert.match(detail, /allowManagementActions && <button className="modal-icon-button favorite-button"/);
  assert.match(detail, /allowManagementActions && <button className="modal-icon-button detail-delete-button"/);
  assert.match(detail, /allowManagementActions && editingPromptLanguage === lang/);
  assert.match(detail, /allowManagementActions && \(addingTag \?/);
  assert.match(detail, /selectedImage \|\| showMutations/);
  assert.equal((detail.match(/\{selectedImage && <a className="modal-icon-button download-button"/g) || []).length, 2);
});
