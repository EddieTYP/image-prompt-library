# Image Prompt Library

[![CI](https://github.com/EddieTYP/image-prompt-library/workflows/CI/badge.svg)](https://github.com/EddieTYP/image-prompt-library/actions/workflows/ci.yml)
[![GitHub Pages demo](https://github.com/EddieTYP/image-prompt-library/workflows/Deploy%20GitHub%20Pages%20demo/badge.svg)](https://github.com/EddieTYP/image-prompt-library/actions/workflows/pages.yml)
[![Release](https://img.shields.io/github/v/tag/EddieTYP/image-prompt-library?sort=semver&label=release)](https://github.com/EddieTYP/image-prompt-library/releases/tag/v0.6.5-beta)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)](LICENSE)

ChatGPT image generation has become good enough that the prompts are worth keeping. The problem is that once you start saving great outputs, screenshots, and variations, there still is not a simple private tool for managing image prompts like a real reference library.

**Image Prompt Library** is a local-first web app for collecting generated images and the prompts behind them. When you create an image worth reusing, save it into your own self-hosted library, add the prompt, organize it into collections and tags, and search it later as a quick visual reference.

Your library stays on your own machine: local SQLite, local image files, no accounts, no cloud sync, and no hosted database required.

**Online Read Only Demo:** <https://eddietyp.github.io/image-prompt-library/> — browse public sample prompts and preview images on GitHub Pages. The online demo is read-only: Add, edit, generation, and private library management are local-only, so install the app locally to create, edit, or generate images for your own full library. Latest v0.6.5 beta refreshes existing sample imports, fixes bilingual prompt variants, and keeps demo title localization read-only/demo-only.

**v0.6 beta highlight:** local installs can connect via **ChatGPT OAuth**, use direct image generation from saved prompts, choose aspect ratio and quality settings, review generated results before saving, then `Attach to current item` or `Save as new item` with editable metadata, smart tag/collection suggestions, source-language pills, and direct image downloads. No hosted account, cloud sync, or public API key is required by the app.

**Beta release:** <https://github.com/EddieTYP/image-prompt-library/releases/tag/v0.6.5-beta> — Refreshes the public demo/sample metadata from awesome-gpt-image-2, fixes bilingual prompt variants, adds demo-only localized card titles, and keeps the v0.6 generation, image action, installer/update, and rollback workflows.

**Project status:** This is a public beta. Core browsing, search, local add/edit, optional local generation, versioned installs, and the read-only online demo are available today.

![Image Prompt Library Cards view](docs/assets/screenshots/card-view-all.png)

The public Online Read Only Demo remains a multilingual provenance-aware prompt vault: 533 public references, two attributed sample sources, English / Traditional Chinese / Simplified Chinese prompt variants, and source/original provenance for every item. The v0.6 beta local app release adds polished generation, Save-as-new metadata, and image action workflows on top of the private install workflow.

## TL;DR for beginners

Think of the app as two folders:

- **The app:** the replaceable program files. The installer puts these in `~/.image-prompt-library`.
- **Your private library:** your prompts, SQLite database, and images. By default this lives in `~/ImagePromptLibrary`.

Prerequisite: install **Python 3.10 or newer**. You do **not** need Node.js for the normal release install.

Install, load starter sample data, and start in three steps:

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash
image-prompt-library sample-data en
image-prompt-library start
```

The starter sample library is available in English, Simplified Chinese, and Traditional Chinese. All three use the same images and prompt references; the difference is the default prompt language and localized collection names.

```bash
image-prompt-library sample-data en       # English
image-prompt-library sample-data zh_hans  # Simplified Chinese
image-prompt-library sample-data zh_hant  # Traditional Chinese
```

Want a larger Traditional Chinese demo library instead? Replace the sample-data step with:

```bash
image-prompt-library sample-data zh_hant awesome-gpt-image-2
```

Then open <http://127.0.0.1:8000/> in your browser.

To print a local health report, run:

```bash
image-prompt-library doctor
```

On macOS, install a launchd user service if you want the app to survive Terminal closure and start when you log in:

```bash
image-prompt-library service install --host 127.0.0.1 --port 8000
```

Use `--host 0.0.0.0` only when you intentionally want LAN access and understand the firewall exposure.

If the `image-prompt-library` command is not found, add `~/.local/bin` to your shell `PATH`, or use the fallback command printed by the installer:

```bash
~/.image-prompt-library/app/current/scripts/appctl.sh start
```

Keep your private library and uninstall only the app:

```bash
image-prompt-library uninstall
```

This removes the app files but keeps your prompts and images in `~/ImagePromptLibrary`, so you can reinstall later.

To delete everything, including your private library, use the explicit destructive command:

```bash
image-prompt-library uninstall --delete-library
```

If you run that from a script or non-interactive shell, add `--yes`:

```bash
image-prompt-library uninstall --delete-library --yes
```

## What it does

- Save generated/reference images together with the prompt text that created them.
- Organize references into collections and tags so good prompts are easy to find again.
- Browse visually in **Explore view**, a thumbnail constellation that spreads images by collection in a style inspired by graph tools like Obsidian.
- Browse densely in **Cards view**, an image-first masonry gallery for scanning many prompt references quickly on desktop and mobile.
- Search across titles, prompts, tags, collections, sources, and notes; see [Searching the library](#searching-the-library) for examples.
- Filter by collection, open a detail view, and copy the prompt with one click.
- Generate New Image from a prompt, or generate a Variant of an existing one with ChatGPT Image 2.0 once you have completed OAuth.
- Keep everything local for privacy and long-term ownership.

## Screenshots

The screenshots below show the main browsing, detail, and local generation flows. The public Online Read Only Demo keeps the mobile Cards/detail improvements from 0.2 and the richer multilingual read-only prompt vault from 0.3, while the v0.6 beta local install path adds the polished ChatGPT image generation, Save-as-new metadata, and image action workflows.

### Generate with ChatGPT OAuth

Once the optional ChatGPT OAuth provider is connected, local installs can generate a new image from a fresh prompt or create a variant from an existing reference. Results land in the local inbox first, where you can attach them to the current item or save them as a new item with editable metadata.

<p>
  <img src="docs/assets/screenshots/generation-provider-connected.jpeg" width="49%" alt="Config drawer showing ChatGPT OAuth connected" />
  <img src="docs/assets/screenshots/generation-standalone-panel.jpeg" width="49%" alt="Standalone Generate image panel with result inbox" />
</p>
<p>
  <img src="docs/assets/screenshots/generation-variant-detail.jpeg" width="49%" alt="Generate variant panel from an existing reference" />
  <img src="docs/assets/screenshots/generation-result-inbox-save-new.jpeg" width="49%" alt="Save generated result as a new item with editable metadata" />
</p>

### Browse with image-first cards

Cards view is designed for fast visual scanning. The current preview uses an image-first layout with a clean title overlay, quick actions, and adaptive image display for mixed portrait, landscape, and tall reference images.

![Cards view showing a filtered sample collection](docs/assets/screenshots/card-view-all.png)

### Mobile-first browsing behavior

On phones, the app defaults to Cards view, uses a stable two-column masonry layout, keeps quick actions touch-visible, and moves the selected collection into a bottom dock instead of crowding the header. Filters open as a full-height drawer, and the detail view keeps prompt tabs and copy/edit controls reachable without switching to a desktop layout.

<p>
  <img src="docs/assets/screenshots/mobile-cards-view.jpg" width="24%" alt="Mobile Cards view with two-column masonry" />
  <img src="docs/assets/screenshots/mobile-filter-drawer.jpg" width="24%" alt="Mobile collection filter drawer" />
  <img src="docs/assets/screenshots/mobile-detail-image.jpg" width="24%" alt="Mobile image-first detail view" />
  <img src="docs/assets/screenshots/mobile-detail-prompt.jpg" width="24%" alt="Mobile prompt detail with language tabs" />
</p>

### Explore your prompt library visually

Explore view gives you a spatial overview of your library. Collections become visual hubs, with image thumbnails arranged around them so you can scan patterns, styles, and prompt families at a glance.

![Explore view showing the full sample library](docs/assets/screenshots/explore-view-home.png)

### Focus on one collection

Filters let you focus the same visual map on a single collection while keeping search, collection context, and the view switcher close at hand.

![Explore view filtered to a technical diagrams collection](docs/assets/screenshots/explore-view-filtered.png)

### Keep the prompt beside the image

The detail view keeps the large image preview, prompt, language tabs, attribution, notes, tags, favorite/edit actions, and one-click prompt copy in one place. On mobile, the detail view becomes image-first with floating controls over the image.

![Reference item detail modal](docs/assets/screenshots/reference-item-detail.png)

## Features

- Local SQLite database and local image files.
- Image storage with originals, previews, and thumbnails.
- Explore mode: thumbnail constellation view for visual browsing.
- Cards mode: image-first masonry/Pinterest-style prompt gallery.
- Search across titles, prompts, tags, collections, sources, and notes; see [Searching the library](#searching-the-library) for examples.
- Collections and tags for organizing references.
- Detail modal with lightweight inline editing, prompt language tabs, source/origin prompt styling, multi-image browsing, generated-image badges, and copy feedback.
- Add/edit modal with English, Traditional Chinese, and Simplified Chinese prompt fields plus metadata and a single source/origin marker.
- Result image and optional reference image uploads.
- Generate images directly in local installs through optional **ChatGPT OAuth** without adding an OpenAI API key to the app.
- Local generation workflow: `Generate variant`, result inbox review, `Attach to current item`, and `Save as new item` with editable metadata before saving.
- Provider-gated generation UI: generation controls stay hidden until a configured/authenticated provider is available, while Add/Edit remains usable without any generation provider.
- Global generation queue drawer for active/succeeded/failed jobs, plus friendlier policy/rate-limit/auth/provider failure messages.
- Phone-friendly Cards behavior: two-column masonry, compact header, touch-visible actions, and bottom selected-collection dock.
- Adaptive card/detail image display for mixed portrait, landscape, and tall reference images.

## Searching the library

Use the search box at the top of the app to narrow the visible prompt references. In the current release, search is plain keyword search across item titles, prompt text, tags, collection names, source metadata, and notes.

Useful examples:

```text
apple
poster design
product photo
awesome-gpt-image-2
電商
```

Search works together with the collection filter: choose a collection from **Filters**, then type a keyword to search inside that collection. The active search and collection filter appear as chips below the toolbar so you can see what is currently limiting the results.

Planned search improvements include an explicit sort control and lightweight query filters that can be mixed with normal keywords, for example:

```text
created:today apple
created:7d model:gpt-image-2 poster
updated:today tag:ecommerce
source:awesome-gpt-image-2 glasses
fav:true cat
has:image packaging
```

Those `key:value` filters are roadmap items and should be documented as available only after the search/sort upgrade ships.

## Requirements

For normal release installs:

- Python 3.10+
- `curl` or a browser to download the installer

For source/development installs:

- Python 3.10+
- Node.js 20+ recommended
- npm

Normal release installs do not require Node.js because tagged release assets include the built frontend.

For clarity: normal release installs do not require Node.js; Node.js/npm are only needed for source/development installs.

## Platform support

- macOS and Linux are the primary supported local-install targets today.
- Windows can run the app stack through **WSL 2** using the same commands as Linux. If the server starts in WSL but your Windows browser cannot open `http://127.0.0.1:8000/`, stop the server with Ctrl-C and run `image-prompt-library start --host 0.0.0.0`, then open `http://localhost:8000/`. Binding to `0.0.0.0` can expose the app outside WSL, so use it only on a trusted machine/network.
- Native Windows PowerShell/CMD is not a supported quick-start path yet because the current helper scripts are Bash scripts and assume Unix-style virtualenv paths such as `.venv/bin/activate`. Native Windows support should use equivalent PowerShell scripts or a Docker/Compose path in a future pass.

## Quick start for normal users

Install the latest tagged release from GitHub Release assets without cloning the repo:

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash
image-prompt-library start
```

Install a specific tagged release instead:

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash -s -- --version v0.6.5-beta
image-prompt-library start
```

Open <http://127.0.0.1:8000/>.

For diagnostics, run:

```bash
image-prompt-library doctor
```

On macOS, install/manage a user launchd service for a long-running local instance:

```bash
image-prompt-library service install --host 127.0.0.1 --port 8000
image-prompt-library service status
image-prompt-library service restart
image-prompt-library service stop
image-prompt-library service start
image-prompt-library service uninstall
```

Service install refuses to overwrite an existing plist for the same label unless you pass `--replace`, so a managed service is not silently replaced during reinstall. Use `--host 0.0.0.0` only when you intentionally want LAN access and understand the firewall exposure.

The installer keeps replaceable app code under:

```text
~/.image-prompt-library/app/versions/<version>
```

Your private prompt library defaults to:

```text
~/ImagePromptLibrary
```

That data directory is separate from app code, so future updates or rollbacks should not overwrite your private SQLite database or images.

Update later with:

```bash
image-prompt-library update
```

Install or switch to a specific version with:

```bash
image-prompt-library update --version v0.6.5-beta
```

Rollback to the previous installed version with:

```bash
image-prompt-library rollback
```

Optionally import the English sample library into your private data directory:

```bash
image-prompt-library sample-data en
```

Uninstall the app files later while keeping your private prompt library:

```bash
image-prompt-library uninstall
```

Delete the private library too only if you are sure you no longer need your local prompts, database, or images:

```bash
image-prompt-library uninstall --delete-library
```

Normal release installs do not require Node.js because the release artifact includes the built frontend. Node.js/npm are only needed for source/development installs.

The selected release must have matching GitHub Release assets: `image-prompt-library-<version>.tar.gz`, `.sha256`, and `.manifest.json`. The installer verifies the SHA256 checksum before switching `app/current` to the new version.

## Local generation workflow

Local installs can optionally connect ChatGPT OAuth for image generation. The GitHub Pages Online Read Only Demo stays read-only and does not expose generation or mutation controls.

Once connected, you can generate a new image from a fresh prompt or create a variant from an existing reference. Generated results go to a review inbox first instead of being silently written into your library. From there, choose `Attach to current item` or `Save as new item` with editable metadata before saving.

No OpenAI API key is required by the app for the ChatGPT OAuth path. Advanced provider configuration is available for users who need it, but the normal flow is handled from the Config drawer.

### Image 2.0 model/quality benchmark

While building Image Prompt Library's Image 2.0 generation workflow, I also benchmarked which Codex/ChatGPT backend tool-calling model and quality setting worked best for this app. The test covered GPT-5.5, GPT-5.4, and GPT-5.3-Codex across Low, Medium, and High quality.

The surprising result was that Low quality was not consistently faster. With the same prompt, GPT-5.5 + Low took 181.4s, while GPT-5.5 + Medium took only 44.6s. Most other combinations were roughly in the 50-60s range, except GPT-5.4 + Low, which was comparatively faster. Subjectively, GPT-5.4 produced the strongest images, followed by GPT-5.5 and then GPT-5.3-Codex.

Based on that benchmark, the recommended default for this beta line is **GPT-5.4 + High**: acceptable speed with the best visual quality in these tests. Users can still change both the tool-calling model and quality setting manually. See the benchmark notes and images in [`docs/generation-matrix-chatgpt-codex-impasto-florals-2026-05-01.md`](docs/generation-matrix-chatgpt-codex-impasto-florals-2026-05-01.md).

## Developer setup from source

Use this path if you want to develop the app, inspect unreleased `main`, or run from a checkout:

```bash
git clone https://github.com/EddieTYP/image-prompt-library.git
cd image-prompt-library
./scripts/setup.sh
./scripts/start.sh
```

Open <http://127.0.0.1:8000/>.

`setup.sh` auto-detects `python3.13`, `python3.12`, `python3.11`, or `python3.10` before falling back to `python3`. On macOS, `/usr/bin/python3` may still be Python 3.9; if setup cannot find a new enough interpreter, install Python 3.10+ and rerun with an explicit interpreter:

```bash
PYTHON=/path/to/python3.12 ./scripts/setup.sh
./scripts/start.sh
```

`start.sh` uses `.venv/bin/python` from setup when available and prints an actionable setup message if Python dependencies are missing.

`scripts/start.sh` builds the frontend and serves the built app through FastAPI, so source local use only needs one server after setup.

## Development mode

For frontend/backend development with Vite hot reload:

```bash
./scripts/dev.sh
```

Open <http://127.0.0.1:5177/>.

Default development ports:

- Backend API: <http://127.0.0.1:8000>
- Vite frontend: <http://127.0.0.1:5177>

## Configuration

Copy `.env.example` to `.env` and edit if needed:

```bash
cp .env.example .env
```

Important settings:

```bash
IMAGE_PROMPT_LIBRARY_PATH=./library
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_PORT=5177
BACKUP_DIR=./backups
```

`IMAGE_PROMPT_LIBRARY_PATH` controls where your private database and images live. The default `./library` is repo-local and intentionally ignored by git. For long-term personal use, you may prefer a durable path such as `~/ImagePromptLibrary`.

## Data layout

Runtime data lives under `IMAGE_PROMPT_LIBRARY_PATH`:

```text
library/db.sqlite       SQLite metadata and full-text search index
library/originals/      original uploaded/imported images
library/previews/       generated preview images
library/thumbs/         generated thumbnail images
```

Do not commit runtime `library/` data to git. It is your private prompt/image collection.

## Add your own prompts & images

1. Start the app.
2. Click `+ Add`.
3. Add a title, prompt text, collection, optional tags, and a required result image.
4. Save the card.
5. Use Cards/Explore, search, filters, and detail view to browse and copy prompts later.

![Add prompt modal](docs/assets/screenshots/add-prompt-modal.png)

## Import and example data

The app starts with an empty private library. Your own `library/` folder contains personal prompt data and images, so it is intentionally ignored by git.

### Try the sample library

For normal release installs, use the installed command so the sample data goes into the installer-managed private library path (`~/ImagePromptLibrary` by default):

```bash
image-prompt-library sample-data en
```

For source/development checkouts, run the repository script directly:

```bash
./scripts/install-sample-data.sh en
```

Then start the app and open <http://127.0.0.1:8000/>.

The installer downloads the sample image ZIP from a public sample-data release and verifies its SHA256 checksum before import. Sample manifests use schema v2 prompt provenance, so each item records one source/original prompt language and any converted or translated variants. When reproducing a sample image, copy the **Origin** prompt where available; it is usually closest to the original result.

The default sample library is based on [`wuyoscar/gpt_image_2_skill`](https://github.com/wuyoscar/gpt_image_2_skill), licensed under **CC BY 4.0**. Thank you to `wuyoscar/gpt_image_2_skill` for the curated ChatGPT image prompt gallery used as the first public sample package.

A second sample package based on [`freestylefly/awesome-gpt-image-2`](https://github.com/freestylefly/awesome-gpt-image-2), licensed under **MIT**, is available with:

```bash
./scripts/install-sample-data.sh zh_hant awesome-gpt-image-2
```

Both are included only as demo/sample content; your own prompt library data remains private and is not part of any sample bundle.

Thank you to `freestylefly/awesome-gpt-image-2` for the larger Chinese prompt/image gallery used as the second public sample package. The Image Prompt Library app code remains AGPL-3.0-or-later; third-party sample prompts/images keep their own upstream attribution and license boundary.

## Backup

Create a timestamped backup archive:

```bash
./scripts/backup.sh
```

The backup includes:

- `library/db.sqlite`
- `library/originals/`
- `library/thumbs/`
- `library/previews/`

Restore by stopping the app, extracting the archive, and replacing the corresponding library directory contents. Keep backups somewhere outside the repo if the library matters to you.

## GitHub Pages Online Read Only Demo

The public Pages deployment is versioned. Use <https://eddietyp.github.io/image-prompt-library/> for the version chooser or <https://eddietyp.github.io/image-prompt-library/v0.6/> for the current 0.6 preview.

The online demo is read-only: Add, edit, generation, and private library management are local-only, so install the app locally to create, edit, or generate images for your own private prompt library. Latest v0.6.5 beta refreshes existing sample imports, fixes bilingual prompt variants, and keeps demo title localization read-only/demo-only.

## License and allowed use

Image Prompt Library's core application code is open source under **AGPL-3.0-or-later**. Copyright (C) 2026 Edward Tsoi. See `NOTICE` for the project copyright notice and `LICENSE` for the full AGPL text.

Commercial licenses are available for organizations that want to use, modify, or host Image Prompt Library under terms outside the AGPL. Contact the maintainer if you need proprietary hosted-product terms or other non-AGPL licensing.

Sample data and third-party assets are licensed separately and retain their original attribution/license terms. The optional sample bundles currently preserve `wuyoscar/gpt_image_2_skill` / **CC BY 4.0** and `freestylefly/awesome-gpt-image-2` / **MIT** attribution; do not treat sample prompts/images as part of the app-code AGPL grant.

Your own local prompt library data remains yours and should not be committed to this repository.

## Privacy and security model

- The app is local-first and stores data on your device.
- There are no user accounts or built-in cloud sync.
- The `/media` route only serves image media directories and should not expose the SQLite database or internal files.
- Binding to `127.0.0.1` keeps the app local to your machine. Only change the host if you understand the LAN exposure implications.

## Troubleshooting

### `./scripts/start.sh` cannot find Python dependencies

Run setup first:

```bash
./scripts/setup.sh
```

### Port already in use

Change `.env`:

```bash
BACKEND_PORT=8001
FRONTEND_PORT=5178
```

Then restart the app.

### Empty library after first start

That is expected for a fresh install. Click `+ Add` to create your first prompt card, or install the optional sample library if you want demo content first.

### Images or database missing after moving folders

Check `IMAGE_PROMPT_LIBRARY_PATH` in `.env`. Your database and image folders must stay together.

## Project status

This is a beta local-first app. Core browse/search/filter/detail/copy/add/edit flows exist, the public Online Read Only Demo is versioned, and the local v0.6 beta adds optional ChatGPT image generation with aspect ratio Auto, image edit/reference support, a review inbox, attach-current-item, save-as-new-item, smart metadata review, and image download/fullscreen actions. Remaining work includes import-flow polish, deeper mobile Explore gestures, and public-release hardening.

For contributor setup, tests, and project structure, see [`CONTRIBUTING.md`](CONTRIBUTING.md).
