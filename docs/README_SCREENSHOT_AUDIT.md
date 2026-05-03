# README Screenshot Audit

This is a local planning note for the README refresh.

## Keep in main README

### `docs/assets/screenshots/public-demo-v0.6-533-references.png`

- Status: keep in the current compact README.
- Why: shows the live public demo with `533 references`, current search/filter chrome, and the public sample gallery.
- Latest update: replaced with the fresh 2526×1227 capture provided during the README screenshot refresh.

### `docs/assets/screenshots/generation-provider-connected.png`

- Status: keep as the compact local-generation screenshot in the main README.
- Why: clearly shows the current **ChatGPT / Codex OAuth** provider label, connected state, and available generation modes.
- Privacy note: account details must stay redacted.

## Generation docs screenshots

The refreshed generation flow is documented in `docs/GENERATION.md` with these current screenshots:

- `generation-provider-unset.png` — Config / Providers panel before OAuth connection.
- `generation-provider-device-url.png` — local device-login step with verification URL and user code.
- `generation-codex-cli-oauth-device.png` — browser approval page; useful because the beta flow surfaces as Codex CLI device authorization.
- `generation-provider-connected.png` — connected provider state; also used by the main README.
- `generation-composer-running.png` — generation composer while a job is running.
- `generation-composer-result.png` — completed generated result in the image-first composer/stage.
- `generation-save-as-new-item.png` — save-as-new review screen with editable metadata and readonly provenance.

## Replace before final polish if possible

### `docs/assets/screenshots/local-generation-studio-banner-v0.7.webp`

- Status: updated for `v0.7.0-beta` root demo/release banner usage.
- Notes: image text now highlights prompt variables and bulk delete.

### `docs/assets/screenshots/card-view-all.png`

- Status: optional historical/feature screenshot.
- Why replace: screenshot appears to come from older sample/category state. It still shows the correct Cards concept, but the README now uses `public-demo-v0.6-533-references.png` for the current public demo.

### `docs/assets/screenshots/reference-item-detail.png`

- Status: candidate for README if refreshed.
- Why: detail view best communicates prompt tabs, source/origin, copy, attribution, and image metadata.
- Recommendation: use one fresh detail screenshot in README or docs after visual QA.

## Move to docs, not main README

### Older generation screenshots

- `generation-provider-connected.jpeg`
- `generation-standalone-panel.jpeg`
- `generation-variant-detail.jpeg`
- `generation-result-inbox-save-new.jpeg`

Reason: useful historical captures, but superseded by the refreshed generation flow screenshots above. `generation-standalone-panel.jpeg` also looks slightly outdated because it exposes internal wording like `Create GenerationJob` and a modal-heavy layout rather than the desired minimal image-first Composer/Stage direction.

Recommended destination: keep only as historical assets unless they are replaced or removed in a later cleanup.

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
