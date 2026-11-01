import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

const source = fs.readFileSync(new URL('../frontend/src/hooks/useItemsQuery.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const tick = () => new Promise(resolve => setImmediate(resolve));
const page = (ids, total, offset = 0) => ({ items: ids.map(id => ({ id })), total, limit: 1000, offset });

function mount() {
  const slots = [], effects = [], requests = [];
  let cursor = 0, pending = [], props = ['', undefined, undefined, 1000, 0, 'updated_desc'];
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
      return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useEffect(callback, deps) {
      const index = cursor++;
      if (!effects[index] || deps.some((value, i) => value !== effects[index].deps[i])) {
        pending.push(() => {
          effects[index]?.cleanup?.();
          effects[index] = { deps, cleanup: callback() };
        });
      }
    },
  };
  const exports = {};
  vm.runInNewContext(compiled, { exports, require: name => name === 'react' ? react : name.includes('api/client')
    ? { api: { items: params => new Promise((resolve, reject) => requests.push({ params, resolve, reject })) } }
    : { DEFAULT_ITEM_SORT: 'updated_desc' } });
  return {
    requests,
    render(nextProps = props) {
      props = nextProps; cursor = 0; pending = [];
      const result = exports.useItemsQuery(...props);
      pending.forEach(run => run());
      return result;
    },
    unmount() { effects.forEach(effect => effect?.cleanup?.()); },
  };
}

test('load more reaches item 1200 and locks rapid duplicate requests', async () => {
  const h = mount(); h.render();
  h.requests[0].resolve(page(Array.from({ length: 1000 }, (_, i) => `item-${i}`), 1200)); await tick();
  const view = h.render();
  const first = view.loadMore(); await view.loadMore();
  assert.equal(h.requests.length, 2);
  assert.equal(h.requests[1].params.offset, 1000);
  h.requests[1].resolve(page(Array.from({ length: 200 }, (_, i) => `item-${1000 + i}`), 1200, 1000));
  assert.equal(await first, 'item-1000');
  const final = h.render();
  assert.equal(final.data.items.length, 1200);
  assert.equal(final.data.items.at(-1).id, 'item-1199');
  assert.equal(final.hasMore, false);
  assert.equal(final.appendVersion, 1);
});

test('failed page retains cards and retries the same offset', async () => {
  const h = mount(); h.render(); h.requests[0].resolve(page(['a'], 3)); await tick();
  const request = h.render().loadMore(); h.requests[1].reject(new Error('offline')); await request;
  const failed = h.render();
  assert.equal(failed.data.items.length, 1);
  assert.match(failed.loadMoreError, /offline/);
  assert.equal(failed.appendVersion, 0);
  const retry = failed.loadMore();
  assert.equal(h.requests[2].params.offset, 1);
  h.requests[2].resolve(page(['b', 'c'], 3, 1)); await retry;
  assert.equal(h.render().data.items.length, 3);
  assert.equal(h.render().appendVersion, 1);
});

test('late old-scope page cannot append or clear the new page lock', async () => {
  const h = mount(); h.render(); h.requests[0].resolve(page(['a'], 3)); await tick();
  const old = h.render().loadMore();
  h.render(['new', undefined, undefined, 1000, 0, 'updated_desc']);
  h.requests[2].resolve(page(['new-a'], 2)); await tick();
  const current = h.render().loadMore();
  h.requests[1].resolve(page(['old-b'], 3, 1)); await old;
  assert.equal(h.render().loadingMore, true);
  assert.equal(h.render().data.items[0].id, 'new-a');
  assert.equal(h.render().appendVersion, 0);
  h.requests[3].resolve(page(['new-b'], 2, 1)); await current;
  assert.deepEqual(Array.from(h.render().data.items, item => item.id), ['new-a', 'new-b']);
  assert.equal(h.render().appendVersion, 1);
});

test('new query resets the append signal even when the first result is unchanged', async () => {
  const h = mount(); h.render(); h.requests[0].resolve(page(['a'], 2)); await tick();
  const next = h.render().loadMore(); h.requests[1].resolve(page(['b'], 2, 1)); await next;
  assert.equal(h.render().appendVersion, 1);
  h.render(['new', undefined, undefined, 1000, 0, 'updated_desc']);
  h.requests[2].resolve(page(['a'], 1)); await tick();
  assert.equal(h.render().appendVersion, 0);
});

test('Explore uses explicit appends and manual loading; pagination focuses a selectable card in selection mode', () => {
  const explore = fs.readFileSync(new URL('../frontend/src/components/ExploreView.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(explore, /IntersectionObserver/);
  assert.match(explore, /if \(appendVersion\) setVisibleCount\(count => count \+ EXPLORE_PAGE_SIZE\)/);
  assert.match(explore, /\[hasActiveSearch, searchQuery, sort, scopeKey\]/);
  const app = fs.readFileSync(new URL('../frontend/src/App.tsx', import.meta.url), 'utf8');
  assert.match(app, /querySelector<HTMLElement>\('\.card-select-action'\) \|\| open/);
});

test('duplicate IDs do not duplicate cards and raw page size advances the offset', async () => {
  const h = mount(); h.render(); h.requests[0].resolve(page(['a'], 4)); await tick();
  const next = h.render().loadMore(); h.requests[1].resolve(page(['a', 'b', 'b'], 5, 1)); await next;
  assert.deepEqual(Array.from(h.render().data.items, item => item.id), ['a', 'b']);
  const last = h.render().loadMore();
  assert.equal(h.requests[2].params.offset, 4);
  h.requests[2].resolve(page([], 5, 4)); await last;
  assert.equal(h.render().hasMore, false);
});

test('unmount invalidates pending appended pages', async () => {
  const h = mount(); h.render(); h.requests[0].resolve(page(['a'], 3)); await tick();
  const next = h.render().loadMore(); h.unmount();
  h.requests[1].resolve(page(['b'], 3, 1));
  assert.equal(await next, undefined);
});

test('long content wraps and gallery space stays separate from the image', () => {
  const css = fs.readFileSync(new URL('../frontend/src/styles.css', import.meta.url), 'utf8');
  assert.match(css, /\.detail-side\{min-width:0/);
  assert.match(css, /\.card-body h3\{overflow-wrap:anywhere;[^}]*-webkit-line-clamp:3/);
  assert.match(css, /\.detail-side \.metadata-inline-edit\{min-width:0;max-width:100%;overflow-wrap:anywhere/);
  assert.match(css, /:has\(\.image-gallery-rail\):not\(\.is-mobile-fullscreen\) \.detail-fullscreen-frame\{height:calc\(100% - 164px\)/);
});
