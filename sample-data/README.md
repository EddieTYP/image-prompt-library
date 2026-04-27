# Sample Data

Image Prompt Library does not commit runtime databases or user media. Optional sample data is provided as a curated bundle for screenshots, demos, and first-run exploration.

Sample installer command for the default package:

```bash
./scripts/install-sample-data.sh zh_hant
# or: ./scripts/install-sample-data.sh zh_hans
# or: ./scripts/install-sample-data.sh en
```

A second sample package (`freestylefly/awesome-gpt-image-2`, Traditional Chinese manifest with source English prompts where available):

```bash
./scripts/install-sample-data.sh zh_hant awesome-gpt-image-2
```

The manifests in `sample-data/manifests/` are kept in git. The image files are distributed separately as release assets so normal clones stay lightweight.

Release assets:

| Package | Release tag | Asset | SHA256 |
| --- | --- | --- | --- |
| `gpt-image-2-skill` | `sample-data-v1` | `image-prompt-library-sample-images-v1.zip` | `8a458f6c8c96079f40fbc46c689e7de0bd2eb464ee7f800f94f3ca60131d5035` |
| `awesome-gpt-image-2` | `sample-data-awesome-gpt-image-2-v1` | `image-prompt-library-awesome-gpt-image-2-sample-images-v1.zip` | `52876b5e051a9b214297b0de7aa403363295f9a478362506dad55ce32755140f` |

The installer verifies the downloaded ZIP against this checksum before import. To test a local ZIP override with checksum verification, pass `SAMPLE_DATA_IMAGE_ZIP_SHA256=<sha256>` together with `SAMPLE_DATA_IMAGE_ZIP=...`.

For local QA without downloading from GitHub, point the installer at a local image ZIP:

```bash
IMAGE_PROMPT_LIBRARY_PATH=.local-work/sample-demo SAMPLE_DATA_IMAGE_ZIP=.local-work/image-prompt-library-sample-images-v1.zip ./scripts/install-sample-data.sh en
IMAGE_PROMPT_LIBRARY_PATH=.local-work/awesome-gpt-image-2-demo SAMPLE_DATA_IMAGE_ZIP=.local-work/image-prompt-library-awesome-gpt-image-2-sample-images-v1.zip ./scripts/install-sample-data.sh zh_hant awesome-gpt-image-2
```

The curated sample sources are `wuyoscar/gpt_image_2_skill` and `freestylefly/awesome-gpt-image-2`. Preserve attribution and review the upstream licenses before publishing screenshots, demo GIFs, or release assets.
