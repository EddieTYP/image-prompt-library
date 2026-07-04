# Security Policy

Image Prompt Library is a local-first public beta. The app is designed to run on your own machine with a local SQLite database and local media files.

## Supported versions

Security fixes target the latest tagged beta release and the latest `main` branch. Older beta releases may receive guidance to update rather than backported fixes.

## Reporting a vulnerability

Please report suspected vulnerabilities privately before opening a public issue.

- Use GitHub's private vulnerability reporting if it is enabled for the repository.
- Otherwise, open a minimal public issue asking for a private contact path, but do not include exploit details, private data, personal images, API keys, or credentials in that issue.

Helpful details include:

- the affected commit or release;
- operating system and Python/Node versions;
- exact setup/run commands;
- whether the app was bound to `127.0.0.1` or exposed on a LAN/public interface;
- reproduction steps and any relevant logs.

Do not include private prompt-library data, personal images, API keys, or credentials in public issues.

## Local-first security expectations

- The default bind address is `127.0.0.1`; changing the host can expose the app to other devices on your network.
- Runtime data under `IMAGE_PROMPT_LIBRARY_PATH` is private user data and should be backed up separately.
- The `/media` route should only serve intended image media directories, never the SQLite database, config files, backups, or arbitrary local paths.
- There is no built-in authentication layer yet, so do not expose the app directly to the public internet.
