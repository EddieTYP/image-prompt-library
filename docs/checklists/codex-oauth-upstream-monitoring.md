# Codex OAuth Upstream Monitoring Checklist

Use this before publishing any release that includes or changes `openai_codex_oauth_native`, and whenever ChatGPT / Codex OAuth Connect stops working on a fresh local install.

## Why this exists

`openai_codex_oauth_native` is an experimental local-only adapter that follows the public OpenAI Codex CLI native OAuth flow. The app uses the public native Codex OAuth client identifier by default, then stores the user's private OAuth tokens separately under `~/.image-prompt-library/auth.json`.

The public client id is not a user secret, but the flow depends on upstream Codex CLI source and ChatGPT/Codex backend behavior. Treat it as an external dependency that can drift.

## Upstream source of truth

Monitor the public `openai/codex` repository:

- `codex-rs/login/src/auth/manager.rs`
  - `CLIENT_ID`
  - `REFRESH_TOKEN_URL`
- `codex-rs/login/src/device_code_auth.rs`
  - `/deviceauth/usercode`
  - `/deviceauth/token`
  - `/codex/device`
  - `/deviceauth/callback`
- `codex-rs/login/src/server.rs`
  - `DEFAULT_ISSUER`
  - `/oauth/token`

Local app constants live in:

- `backend/services/openai_codex_native.py`

## Automated drift check

Run this first. It fetches upstream source from `openai/codex` and compares it with local constants:

```bash
scripts/check-codex-oauth-upstream.py
```

Machine-readable output:

```bash
scripts/check-codex-oauth-upstream.py --json
```

Check a specific upstream ref/tag/commit:

```bash
scripts/check-codex-oauth-upstream.py --ref main
```

Check against a local Codex checkout or fixture:

```bash
scripts/check-codex-oauth-upstream.py --upstream-dir /path/to/codex
```

Expected result before release:

```text
overall: OK
```

If the script reports `DRIFT DETECTED`, do not publish a release until the drift is understood and either the app is updated or the release notes call out the provider breakage.

## Optional no-token live smoke

This makes a no-token request to the device-code start endpoint using the local default client id. It does not require or print user OAuth tokens.

```bash
scripts/check-codex-oauth-upstream.py --live-device-smoke
```

Expected live-smoke result:

- HTTP 200
- `user_code` present
- `device_auth_id` present
- `interval` present

If this fails, likely causes include:

- upstream revoked or changed the native client id
- device-code endpoint changed
- required request payload changed
- network / Cloudflare / regional block

## Manual authenticated QA

Only run this locally with a real account. Never commit `~/.image-prompt-library/auth.json` or paste tokens into issues, logs, docs, or chat.

1. Start the local app.
2. Open the Config drawer.
3. Confirm fresh state is `Not connected`, not `Not configured`.
4. Click `Connect`.
5. Complete ChatGPT/Codex device login in the browser.
6. Confirm provider status becomes `Connected`.
7. Create or open a prompt item.
8. Run a small `Generate variant` job.
9. Confirm generated output appears in the GenerationJob result inbox.
10. Confirm `Attach to current item` and `Save as new item` still work.

## Token/privacy guardrails

Before release, confirm:

- `GET /api/generation-providers/openai-codex-native/status` never returns `access_token` or `refresh_token`.
- `~/.image-prompt-library/auth.json` remains outside the library/export/demo data path.
- `auth.json` is not included in sample bundles, release tarballs, GitHub Pages exports, screenshots, or logs.
- Status/error messages distinguish `not_connected` from upstream/provider failures.

## Release gate

Before publishing beta release assets:

- [ ] `scripts/check-codex-oauth-upstream.py` passes.
- [ ] Optional: `scripts/check-codex-oauth-upstream.py --live-device-smoke` passes.
- [ ] `python -m pytest tests/test_codex_oauth_upstream_drift.py tests/test_openai_codex_native.py -q` passes.
- [ ] Full test suite passes.
- [ ] Frontend local and demo builds pass.
- [ ] Fresh install provider state is `Not connected` with Connect enabled.
- [ ] No token/client secret material appears in logs or API responses.

## Current local expected values

At the time this checklist was added, the app expected:

- Issuer: `https://auth.openai.com`
- Token URL: `https://auth.openai.com/oauth/token`
- Verification URL: `https://auth.openai.com/codex/device`
- Device user-code suffix: `/deviceauth/usercode`
- Device token suffix: `/deviceauth/token`
- Redirect suffix: `/deviceauth/callback`

Do not manually copy user-local config values into docs or source. The default client id should be traced back to the public upstream Codex CLI source, not Edward's local config.
