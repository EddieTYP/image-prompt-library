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
const { downloadFileName, imageDisplayPath, selectPrimaryImage } = await importTypescript('../frontend/src/utils/images.ts');
const { generationFailure } = await importTypescript('../frontend/src/utils/generationFailures.ts');

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
  assert.equal(downloadFileName('  Poster / Study  ', 'preview.webp?size=large'), 'poster-study.webp');
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

test('frontend shell declares a mobile viewport and root mount point', async () => {
  const html = await readFile(new URL('../frontend/index.html', import.meta.url), 'utf8');

  assert.match(html, /name="viewport" content="width=device-width, initial-scale=1"/);
  assert.match(html, /<div id="root"><\/div>/);
});
