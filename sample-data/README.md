# Sample Data

Image Prompt Library does not commit runtime databases or user media. Optional sample data is provided as a curated bundle for screenshots, demos, and first-run exploration.

Planned user command:

```bash
./scripts/install-sample-data.sh zh_hant
# or: ./scripts/install-sample-data.sh zh_hans
# or: ./scripts/install-sample-data.sh en
```

The manifests in `sample-data/manifests/` are kept in git. The image files should be distributed separately as a GitHub Release asset, for example `image-prompt-library-sample-images-v1.zip`, so normal clones stay lightweight.

For local QA before the release asset exists, point the installer at a local image ZIP:

```bash
IMAGE_PROMPT_LIBRARY_PATH=.local-work/sample-demo SAMPLE_DATA_IMAGE_ZIP=.local-work/image-prompt-library-sample-images-v1.zip ./scripts/install-sample-data.sh en
```

The current curated sample source is `wuyoscar/gpt_image_2_skill`. Preserve attribution and review the upstream license before publishing screenshots, demo GIFs, or release assets.
