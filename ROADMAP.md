# Roadmap

## Public AGPL local-install MVP

Goal: make Image Prompt Library easy for someone to clone from GitHub, run on their own device, and use as an open-source local-first prompt/image manager under AGPL-3.0-or-later. Commercial licenses are available for organizations that need terms outside the AGPL.

### Must-have before public alpha

- Public-facing README with generic install instructions and no machine-specific absolute paths.
- One-command setup and start scripts.
- Clear `.env.example` configuration for library path, host, and ports.
- Friendly first-run behavior with an empty library and obvious Add CTA.
- Backup and restore guidance for runtime data.
- Smoke-test script for a running local instance.
- Tests/build passing from a fresh checkout.
- Runtime data ignored by git.
- AGPL-3.0-or-later license wording plus clear commercial license option for non-AGPL terms.
- `/media` route must not expose database, config, or internal files.

### Correctness hardening

- Prefer `result_image` for card/detail hero images.
- Treat only `result_image` as satisfying required result-image checks.
- Add DB-level validation for image roles.
- Clean up or roll back prompt-only items if required image upload fails.
- Verify optional sample-library install idempotency.

## Next release preview

The next release is expected to focus on a mobile-native browsing and management experience:

- Mobile opens into Cards view by default when no previous preference is saved.
- Cards use a touch-first dense layout: roughly two columns on narrow phones and three columns on larger phones, with visible copy/favorite/edit actions.
- Explore becomes a contained mobile canvas: one-finger pan, two-finger pinch zoom, and no whole-page pinch distortion while exploring.
- Mobile Explore uses a more vertical thumbnail constellation layout instead of a wide desktop-style map.
- Detail view uses a mobile stack: image on top, close floating at the image top-right, favorite/edit floating at the image bottom-right, and prompt/metadata/tags below.
- Filters, Config, and Manage use full-height mobile drawers.
- Mobile management remains supported: add/edit, result image upload, optional reference image, multilingual prompts, tags, favorite, and archive/delete.

### Nice-to-have after public alpha

- Native Windows PowerShell scripts or a Docker Compose local install path; WSL 2 is the practical Windows route for now.
- Additional sample/demo packs or screenshots beyond the current `sample-data-v1` bundle.
- Export/import backup archive workflow in the UI.
- Full interface language setting.
- Optional semantic/vector search.

## Current non-goals

- Hosted SaaS accounts.
- Built-in cloud sync.
- Public prompt sharing.
- Committing user runtime data into the repository.
