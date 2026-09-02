# Image Prompt Library

[![CI](https://github.com/EddieTYP/image-prompt-library/workflows/CI/badge.svg)](https://github.com/EddieTYP/image-prompt-library/actions/workflows/ci.yml)
[![GitHub Pages demo](https://github.com/EddieTYP/image-prompt-library/workflows/Deploy%20GitHub%20Pages%20demo/badge.svg)](https://github.com/EddieTYP/image-prompt-library/actions/workflows/pages.yml)
[![Release](https://img.shields.io/github/v/release/EddieTYP/image-prompt-library?label=release)](https://github.com/EddieTYP/image-prompt-library/releases/latest)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)](LICENSE)

**English** · [繁體中文](README_zh-TW.md) · [简体中文](README_zh-CN.md)

**Image Prompt Library** is a local-first app for saving images with their prompts, sources, and notes. Browse visually, organize cards into collections and tags, and find a prompt when you want to use it again.

Your library uses local SQLite and local image files. You do not need an account to save, search, or organize it. Optional ChatGPT and Grok connections let you generate images and suggest titles; those requests run on the provider's servers, not on your computer.

![Library view with saved image and prompt cards](docs/assets/screenshots/local-app-library-overview.jpg)

*The local app with optional sample references loaded. A new library starts empty.*

## Release status

`v0.10.2` is the current stable release, available from [GitHub Latest](https://github.com/EddieTYP/image-prompt-library/releases/latest). **Grok, provider-aware title suggestions, and the multi-image workflows below are coming in v0.11.0**; they are not in the current stable download. See the [v0.11.0 release notes](docs/releases/v0.11.0.md) for the full changes.

## Quick start

### Windows

Requires Windows 10/11, PowerShell 5.1+, and **Python 3.10+**. Install Python first; the installer does not install it for you.

```powershell
irm https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.ps1 | iex
```

The installer starts the app in the background and opens your browser. Use `image-prompt-library stop` to stop it.

### macOS, Linux, and WSL 2

Requires **Python 3.10+** and `curl`. Release installs do not require Node.js.

```bash
curl -fsSL https://raw.githubusercontent.com/EddieTYP/image-prompt-library/main/scripts/install.sh | bash
image-prompt-library start
```

Keep the terminal open and visit [http://127.0.0.1:8000](http://127.0.0.1:8000). Press `Ctrl-C` in that terminal to stop the server.

For an inspect-before-running installation, updates, rollback, or uninstall, see the [installation guide](docs/INSTALLATION.md). If the app does not start, run `image-prompt-library status` and `image-prompt-library doctor`, then check [Troubleshooting](docs/TROUBLESHOOTING.md).

### Save your first prompt

A fresh local library starts empty. Choose **+ Add**, add an image and prompt, give the card a title, and save it. Collections, tags, notes, and source links are optional.

To browse examples first, import one of the optional sample bundles:

```bash
image-prompt-library sample-data en       # English collection names
image-prompt-library sample-data zh_hans  # Simplified Chinese collection names
image-prompt-library sample-data zh_hant  # Traditional Chinese collection names
```

Run only the command for your preferred collection language. Source titles, prompts, and available language variants are preserved. A larger Traditional Chinese pack is also available:

```bash
image-prompt-library sample-data zh_hant awesome-gpt-image-2
```

## Browse and organize

- **Explore** groups image references by collection; **Library** provides the full card view and editing controls.
- Keep original and translated prompts together. Select a language variant to read or copy it.
- Use keyword search across titles, prompts, tags, collections, sources, and notes, or combine it with structured search filters such as `tag:portrait`, `collection:architecture`, and `sort:title`.
- Select several cards to tag, move, favorite, archive, or delete them. In v0.11.0, **Tag** suggests existing tags and **Move** lets you search for a collection instead of typing its exact name.
- In v0.11.0, keep multiple images in one card. In **Edit**, choose the cover image, reorder images, change result/reference roles, or remove one image without deleting the whole card.

![Explore view organized by collection](docs/assets/screenshots/local-app-explore.jpg)

*Explore is for browsing collections; Library is for managing individual cards.*

![Reference detail with an image, prompt variants, tags, and source](docs/assets/screenshots/local-app-detail.jpg)

*A card keeps its images, prompt variants, and source together. New generated images also retain their provider and model details.*

## Generate images with ChatGPT or Grok

Generation is optional and requires a local install and an eligible provider account. **Grok OAuth is experimental in v0.11.0.** Account access, usage limits, and charges are controlled by the provider; connecting does not guarantee free or unlimited generation. No API key is required by these OAuth connections.

1. Open **Config → Providers**, choose **ChatGPT / Codex OAuth** or **Grok OAuth**, and complete the browser authorization. Return to the app and choose **Check authorization** if prompted.
2. Choose a **Default AI provider**. This is saved in the current browser. You can override it for a generation session without changing the default.
3. Open **Generate**, enter a prompt, and optionally add reference images. Reusable prompts can include `{{variables}}`, such as `{{subject}}`; fill them before generating.
4. Choose the available ratio, quality, and other controls. Generate one image or a set of 3, 5, or 10, then review completed results from the **Work queue**.
5. Use **Save as new item**, or attach a result to its unchanged source card. When reviewing a set, later results can join the card created from the first saved result, so the images stay together.

Grok uses `grok-imagine-image-2.0`, with Low/Medium quality, 1K/2K resolution, and up to three reference images. ChatGPT supports up to four references and has its own model and quality choices. Switching provider updates the available controls.

![Grok selected in the generation provider menu](docs/assets/screenshots/generation-grok-provider.png)

*Choose a provider in the generation window. This is separate from the default saved in Config.*

### Suggest a title

In **Add**, **Edit**, or a generated-result save form, choose **Suggest title** to request a short title from the prompt text. Review the suggestion and choose **Use title** to apply it; your current title is not overwritten automatically.

Add/Edit uses your default AI provider. A generated result uses the provider that made it, shown as **via ChatGPT** or **via Grok**. If the chosen provider is disconnected, the app asks you to reconnect; it does not silently send the prompt to another provider.

See the [generation guide](docs/GENERATION.md) for connection steps, reference-image limits, result handling, and troubleshooting.

## Online read-only demo

[Open the demo](https://eddietyp.github.io/image-prompt-library/) to browse collections, search examples, and copy public sample prompts without installing anything.

![Online read-only demo showing Explore collections](docs/assets/screenshots/public-demo-explore.png)

*The hosted demo uses public sample data. Editing, private-library management, and generation are available only in a local install.*

## Sample data and attribution

The demo references and optional sample bundles retain their source links and license information. The sample prompts and artwork are not original Image Prompt Library content.

| Source | License | Pack |
| --- | --- | --- |
| [wuyoscar/gpt_image_2_skill](https://github.com/wuyoscar/gpt_image_2_skill) | CC BY 4.0 | Starter pack |
| [freestylefly/awesome-gpt-image-2](https://github.com/freestylefly/awesome-gpt-image-2) | MIT | Larger prompt/image gallery |

See [sample-data/README.md](sample-data/README.md) for pack details and checksums.

## Privacy

- Keep your own private prompt/image library on your computer. There is no hosted user database or built-in cloud sync.
- Image generation sends the entered prompt and selected reference images to the provider you choose. Title suggestions send only prompt text—not your images, existing title, tags, or notes.
- Provider credentials are stored separately from the library and excluded from portable backups and sample exports.
- The app listens on `127.0.0.1` by default. Do not expose it to a network unless you understand the access risks.

## Documentation

- [Installation and updates](docs/INSTALLATION.md)
- [Image generation and title suggestions](docs/GENERATION.md)
- [Backup and restore](docs/BACKUP_AND_RESTORE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Development setup](docs/DEVELOPMENT.md) and [Contributing](CONTRIBUTING.md)
- [Roadmap](ROADMAP.md)

## License

Application code is **AGPL-3.0-or-later**. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Sample data and third-party assets have separate licenses, listed above.

Commercial licenses are available by arrangement with the maintainer for use under terms other than the AGPL.
