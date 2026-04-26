# Contributing

Thanks for considering a contribution to Image Prompt Library.

This project is a Local-first prompt/image reference manager. Please preserve the privacy-first design: user runtime data belongs on the user's device and should not be committed, uploaded, or sent to third-party services by default.

## License model

The core application code is licensed under **AGPL-3.0-or-later**. By contributing, you agree that your contribution is submitted under AGPL-3.0-or-later and may be included in versions distributed under alternative/commercial licensing terms by the project maintainer.

Sample data and third-party assets are licensed separately and retain their original attribution/license terms.


## Local setup

```bash
./scripts/setup.sh
./scripts/dev.sh
```

For single-service local mode:

```bash
./scripts/start.sh
```

## Run tests

Before opening a PR, run:

```bash
source .venv/bin/activate
python -m pytest -q
npm run build
```

If you have a running local server, also run:

```bash
./scripts/smoke-test.sh
```

## Development guidelines

- Keep runtime data out of git:
  - `library/db.sqlite`
  - `library/db.sqlite-*`
  - `library/originals/`
  - `library/thumbs/`
  - `library/previews/`
  - `backups/`
- Avoid hardcoded absolute paths in public docs or scripts.
- Keep `/media` limited to intended image media directories; never expose the SQLite DB or internal files.
- Prefer small, tested changes.
- Add regression tests for bug fixes and public-install behavior.
- Preserve the accepted browsing model: Explore is a thumbnail constellation; Cards is adaptive masonry.

## Reporting issues

When reporting a bug, include:

- OS and browser
- Python and Node versions
- Whether you use dev mode or `scripts/start.sh`
- Steps to reproduce
- Console/server error output if available
- Whether your library is empty, manually created, or imported

Do not attach private prompt/image data unless you intentionally want it public.
