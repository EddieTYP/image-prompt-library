# README Screenshot Audit

This is a local planning note for the README refresh.

## Keep in main README

### `docs/assets/screenshots/public-demo-v0.6-533-references.png`

- Status: keep in the current compact README draft.
- Why: shows the live public demo with `533 references`, current search/filter chrome, and the public sample gallery.

### `docs/assets/screenshots/generation-provider-connected.jpeg`

- Status: keep as a compact local-generation screenshot for now.
- Why: illustrates the ChatGPT OAuth connection step without exposing the older `Create GenerationJob` wording.

## Replace before final polish if possible

### `docs/assets/screenshots/local-generation-studio-banner.webp`

- Status: visually strong but currently not used in the compact README draft.
- Why replace: image text says `v0.6.0-beta`, while current public release is `v0.6.5-beta`.
- Recommendation: regenerate without a hard-coded version, or update to current release before using as the README hero.

### `docs/assets/screenshots/card-view-all.png`

- Status: optional historical/feature screenshot.
- Why replace: screenshot appears to come from older sample/category state. It still shows the correct Cards concept, but the README now uses `public-demo-v0.6-533-references.png` for the current public demo.

### `docs/assets/screenshots/reference-item-detail.png`

- Status: candidate for README if refreshed.
- Why: detail view best communicates prompt tabs, source/origin, copy, attribution, and image metadata.
- Recommendation: use one fresh detail screenshot in README or docs after visual QA.

## Move to docs, not main README

### Generation screenshots

- `generation-provider-connected.jpeg`
- `generation-standalone-panel.jpeg`
- `generation-variant-detail.jpeg`
- `generation-result-inbox-save-new.jpeg`

Reason: useful for generation documentation, but too heavy for a compact README. `generation-standalone-panel.jpeg` also looks slightly outdated because it exposes internal wording like `Create GenerationJob` and a modal-heavy layout rather than the desired minimal image-first Composer/Stage direction.

Recommended destination: `docs/GENERATION.md` after screenshot refresh.

### Mobile screenshots

- `mobile-cards-view.jpg`
- `mobile-filter-drawer.jpg`
- `mobile-detail-image.jpg`
- `mobile-detail-prompt.jpg`

Reason: useful proof of mobile support, but four phone screenshots are too much for the main README.

Recommended destination: a future `docs/MOBILE.md` or `docs/PROJECT_STATUS.md` if mobile UX needs detailed documentation.

### Explore screenshots

- `explore-view-home.png`
- `explore-view-filtered.png`

Reason: still useful, but README can mention Explore without showing multiple screenshots.

Recommended destination: `docs/DEVELOPMENT.md`, `docs/PROJECT_STATUS.md`, or a future feature guide.

### Add prompt screenshot

- `add-prompt-modal.png`

Reason: useful for local usage docs, not necessary in a compact README.

Recommended destination: `docs/DEVELOPMENT.md` or a future user guide.
