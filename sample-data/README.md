# Sample Data

Image Prompt Library does not commit runtime databases or user media. Optional sample data is provided as a curated bundle for screenshots, demos, and first-run exploration.

Sample installer command for normal release installs:

```bash
image-prompt-library sample-data zh_hant
# or: image-prompt-library sample-data zh_hans
# or: image-prompt-library sample-data en
```

Source/development checkout command for the default package:

```bash
./scripts/install-sample-data.sh zh_hant
# or: ./scripts/install-sample-data.sh zh_hans
# or: ./scripts/install-sample-data.sh en
```

A second sample package (`freestylefly/awesome-gpt-image-2`, Traditional Chinese manifest with source-language provenance and derived English translation prompts):

```bash
./scripts/install-sample-data.sh zh_hant awesome-gpt-image-2
```

The manifests in `sample-data/manifests/` are kept in git. The image files are distributed separately as release assets so normal clones stay lightweight. Sample items include available prompt variants; many include English, Traditional Chinese, and Simplified Chinese, while some upstream items are Chinese-only. Source/original text and derived machine translations or OpenCC conversions are marked in schema v2 prompt provenance. To refill missing variants during curation, install the optional curation dependencies and run:

Curated sample manifests and image archives do not contain app-owned OAuth credentials, provider config, or device-login/session state.

```bash
python -m pip install deep-translator opencc-python-reimplemented
python backend/services/fill_sample_manifest_translations.py
```

Release assets:

| Package | Release tag | Asset | SHA256 |
| --- | --- | --- | --- |
| `gpt-image-2-skill` | `sample-data-v1` | `image-prompt-library-sample-images-v1.zip` | `8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035` |
| `awesome-gpt-image-2` | `sample-data-awesome-gpt-image-2-v1` | `image-prompt-library-awesome-gpt-image-2-sample-images-v1.zip` | `153714b7611524d7b98b4b0452baa86c8d05053477bb670b731953e8d26a8c9c` |

The installer verifies the downloaded ZIP against this checksum before import. To test a local ZIP override with checksum verification, pass `SAMPLE_DATA_IMAGE_ZIP_SHA256=<sha256>` together with `SAMPLE_DATA_IMAGE_ZIP=...`.

## Build the public web demo

Download both image packages listed above, then run from the repository root:

```bash
python scripts/export-demo-data.py --sample-images image-prompt-library-sample-images-v1.zip --awesome-images image-prompt-library-awesome-gpt-image-2-sample-images-v1.zip
```

The exporter verifies both archives against their pinned checksums and rebuilds the sample data in a temporary library using the checked-in Traditional Chinese manifests. It never reads your existing Library or `IMAGE_PROMPT_LIBRARY_PATH`, so private edits and images added to sample items cannot enter the demo. Modified archives are rejected; there is no checksum override. Output goes to `frontend/public/demo-data` unless `--output` is supplied. Review the resulting public assets before publishing; the exporter does not deploy them.

For local QA without downloading from GitHub, point the installer at a local image ZIP:

```bash
IMAGE_PROMPT_LIBRARY_PATH=.local-work/sample-demo SAMPLE_DATA_IMAGE_ZIP=.local-work/image-prompt-library-sample-images-v1.zip ./scripts/install-sample-data.sh en
IMAGE_PROMPT_LIBRARY_PATH=.local-work/awesome-gpt-image-2-demo SAMPLE_DATA_IMAGE_ZIP=.local-work/image-prompt-library-awesome-gpt-image-2-sample-images-v1.zip ./scripts/install-sample-data.sh zh_hant awesome-gpt-image-2
```

The curated sample sources are `wuyoscar/gpt_image_2_skill` and `freestylefly/awesome-gpt-image-2`. Preserve attribution and review the upstream licenses before publishing screenshots, demo GIFs, or release assets.
