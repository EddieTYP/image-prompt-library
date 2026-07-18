from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_runs_full_public_alpha_checks():
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow_path.exists()
    workflow = workflow_path.read_text()

    assert "name: CI" in workflow
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "actions/checkout@v5" in workflow
    assert "actions/setup-node@v5" in workflow
    assert "node-version: 24" in workflow
    assert "actions/setup-python@v6" in workflow
    assert "python-version: '3.11'" in workflow
    assert "python -m pip install -e '.[dev]'" in workflow
    assert "npm install" in workflow
    assert "python -m pytest -q" in workflow
    assert "npm run build" in workflow
    assert "npm run build:demo" in workflow


def test_alpha_release_notes_are_public_safe_and_actionable():
    notes_path = ROOT / "docs" / "releases" / "v0.1.0-alpha.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.1.0-alpha" in notes
    assert "https://eddietyp.github.io/image-prompt-library/" in notes
    assert "read-only online sandbox" in notes
    assert "compressed" in notes
    assert "local-first" in notes
    assert "SQLite" in notes
    assert "wuyoscar/gpt_image_2_skill" in notes
    assert "CC BY 4.0" in notes
    assert "AGPL-3.0-or-later" in notes
    assert "Commercial licenses" in notes
    assert "Known limitations" in notes
    assert "Python 3.10+" in notes
    assert "./scripts/setup.sh" in notes
    assert "./scripts/start.sh" in notes
    assert "./scripts/install-sample-data.sh en" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()


def test_v02_release_notes_describe_mobile_preview_and_versioned_pages():
    notes_path = ROOT / "docs" / "releases" / "v0.2.0-alpha.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.2.0-alpha" in notes
    assert "current 0.2 preview" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.2/" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.1/" in notes
    assert "two-column masonry" in notes
    assert "selected-collection dock" in notes
    assert "Versioned GitHub Pages" in notes
    assert "`/` is a lightweight version chooser" in notes
    assert "read-only online sandboxes" in notes
    assert "AGPL-3.0-or-later" in notes
    assert "wuyoscar/gpt_image_2_skill" in notes
    assert "freestylefly/awesome-gpt-image-2" in notes
    assert "Python 3.10+" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()


def test_v03_release_notes_describe_multilingual_provenance_vault():
    notes_path = ROOT / "docs" / "releases" / "v0.3.0-alpha.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.3.0-alpha" in notes
    assert "Multilingual provenance-aware prompt vault" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.3/" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.2/" in notes
    assert "510 references" in notes
    assert "English / Traditional Chinese / Simplified Chinese" in notes
    assert "schema v2" in notes
    assert "source/original prompt" in notes
    assert "machine translations" in notes
    assert "OpenCC script conversions" in notes
    assert "wuyoscar/gpt_image_2_skill" in notes
    assert "freestylefly/awesome-gpt-image-2" in notes
    assert "read-only" in notes
    assert "local installation" in notes
    assert "AGPL-3.0-or-later" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()

def test_release_assets_workflow_packages_only_current_version_assets():
    workflow_path = ROOT / ".github" / "workflows" / "release-assets.yml"
    assert workflow_path.exists()
    workflow = workflow_path.read_text()

    assert "rm -rf dist-release" in workflow
    assert 'scripts/package-release.sh "$VERSION" --skip-build' in workflow
    assert "dist-release/image-prompt-library-${{ env.VERSION }}.tar.gz" in workflow
    assert "dist-release/image-prompt-library-${{ env.VERSION }}.tar.gz.sha256" in workflow
    assert "dist-release/image-prompt-library-${{ env.VERSION }}.manifest.json" in workflow
    assert 'test "$GITHUB_SHA" = "$HEAD_SHA"' in workflow
    assert 'gh api --paginate --slurp "repos/$GITHUB_REPOSITORY/releases?per_page=100"' in workflow
    assert 'releases/$RELEASE_ID' in workflow
    assert "Existing release contains unknown or duplicate assets" in workflow
    assert "RESUME_PUBLISHED" in workflow
    assert "if: env.RESUME_PUBLISHED != 'true'" in workflow
    assert "for attempt in 1 2 3 4 5" in workflow
    assert "target_commitish:" not in workflow
    assert "npm run test:frontend" in workflow
    assert "push:" not in workflow
    assert "refs/heads/main" in workflow
    assert "ref: ${{ github.sha }}" in workflow
    assert "token: ${{ github.token }}" in workflow
    assert "persist-credentials: false" in workflow
    assert "group: release-publication" in workflow
    assert "Refs created by GITHUB_TOKEN do not recursively trigger this workflow" in workflow
    assert 'if [ "$GITHUB_REF" != "refs/heads/main" ]' in workflow
    assert "Release candidates must be dispatched from main" in workflow
    assert "IS_PRERELEASE=true" in workflow
    assert "REQUESTED_PRERELEASE" not in workflow
    assert "Create exact release tag after local verification" in workflow
    assert 'if: env.CREATE_TAG == \'true\'' in workflow
    assert 'gh api --method POST "repos/$GITHUB_REPOSITORY/git/refs"' in workflow
    assert '-f ref="refs/tags/$VERSION" -f sha="$SOURCE_SHA"' in workflow
    assert "GitHub did not create the release tag at the verified source commit" in workflow
    assert "An existing GitHub release has no matching tag" in workflow
    assert workflow.index("Package and verify release assets") < workflow.index("Create exact release tag after local verification")
    assert workflow.index("Create exact release tag after local verification") < workflow.index("Upload assets to a draft release")
    assert "Revalidate remote tag before release upload" in workflow
    assert workflow.count('git ls-remote origin "refs/tags/$VERSION^{}"') == 2
    assert "for attempt in 1 2 3 4 5" in workflow
    assert '"$IS_PRERELEASE" "$RUNNER_TEMP/assets.tsv"' in workflow
    assert 'expected_prerelease = prerelease_value.lower() == "true"' in workflow
    assert 'expected_prerelease = "-" in version' not in workflow
    assert workflow.count('--source-sha "$SOURCE_SHA"') == 2

    contributing = (ROOT / "CONTRIBUTING.md").read_text()
    assert "Manual release workflow dispatches are candidate-only" in contributing
    assert "Release candidate install update rollback smoke" in contributing
    assert "Leave the release marked as a prerelease if any platform fails" in contributing
    assert "prerelease=false" in contributing
    assert "make_latest=true" in contributing
    assert "do not retag or re-upload" in contributing


def test_release_candidate_smoke_uses_public_assets_and_default_user_paths():
    workflow_path = ROOT / ".github" / "workflows" / "release-candidate-smoke.yml"
    assert workflow_path.exists()
    workflow = workflow_path.read_text()

    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "group: release-publication" in workflow
    assert "ubuntu-latest" in workflow
    assert "macos-latest" in workflow
    assert "windows-latest" in workflow
    assert "fail-fast: false" in workflow
    assert 'default: \'v0.8.0\'' in workflow
    assert "Candidate is not the requested published prerelease" in workflow
    assert "Candidate assets are not the exact expected set" in workflow
    assert "gh release download" in workflow
    assert "persist-credentials: false" in workflow
    assert "unset GH_TOKEN" in workflow
    assert '--source-sha "$TAG_SHA" --capability posix-shell-v1' in workflow
    assert 'test ! -e "$HOME/.image-prompt-library"' in workflow
    assert 'test ! -e "$HOME/ImagePromptLibrary"' in workflow
    assert 'bash "$installer" --version "$BASELINE_VERSION"' in workflow
    assert '"$app" update --version "$CANDIDATE_VERSION"' in workflow
    assert 'if "$app" rollback; then' in workflow
    assert 'Join-Path $env:LOCALAPPDATA "ImagePromptLibrary"' in workflow
    assert 'Join-Path $env:USERPROFILE "ImagePromptLibrary"' in workflow
    assert "-NoStart -NoBrowser" in workflow
    assert 'Invoke-App -Arguments @("update", "--version", $env:CANDIDATE_VERSION)' in workflow
    assert 'Invoke-App -Arguments @("rollback")' in workflow
    assert "release-smoke-sentinel.txt" in workflow
    assert "IMAGE_PROMPT_LIBRARY_PREFIX" not in workflow
    assert "IMAGE_PROMPT_LIBRARY_PATH" not in workflow
    assert "The promotable candidate must use a bare SemVer tag" in workflow
    assert "contents: write" not in workflow
    assert "prerelease=false" not in workflow


def test_v081_release_notes_describe_safety_and_legacy_posix_boundary():
    notes_path = ROOT / "docs" / "releases" / "v0.8.1.md"
    assert notes_path.exists()
    notes = notes_path.read_text(encoding="utf-8")

    assert "GenerationJob.metadata.error_kind" in notes
    assert "Config → Providers" in notes
    assert "OAuth and provider configuration paths" in notes
    assert "atomic pointer replacement" in notes
    assert "exact source commit" in notes
    assert "posix-shell-v1" in notes
    assert "fails closed" in notes
    assert "legacy shell-evaluated `.env`" in notes
    assert "windows-latest" in notes
    assert "macos-latest" in notes
    assert "ubuntu-latest" in notes
    assert "paid image-generation request" in notes


def test_v04_release_notes_describe_chatgpt_oauth_generation_and_installer():
    notes_path = ROOT / "docs" / "releases" / "v0.4.0-alpha.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.4.0-alpha" in notes
    assert "ChatGPT OAuth" in notes
    assert "direct image generation" in notes
    assert "Online Read Only Demo" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.4/" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.3/" in notes
    assert "openai_codex_oauth_native" in notes
    assert "GenerationJob result inbox" in notes
    assert "Save as new item" in notes
    assert "versioned release installer" in notes
    assert "--version" in notes
    assert "image-prompt-library update --version v0.4.0-alpha" in notes
    assert "image-prompt-library rollback" in notes
    assert "131" in notes
    assert "AGPL-3.0-or-later" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()

def test_v05_release_notes_describe_local_generation_studio_beta():
    notes_path = ROOT / "docs" / "releases" / "v0.5.0-beta.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.5.0-beta" in notes
    assert "Local Generation Studio" in notes
    assert "Online Read Only Demo" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.4/" in notes
    assert "openai_codex_oauth_native" in notes
    assert "aspect ratio" in notes
    assert "Auto`, `Standard`, and `High`" in notes
    assert "two concurrent jobs" in notes
    assert "Cancel" in notes
    assert "cancelled" in notes
    assert "soft cancellation" in notes
    assert "image-prompt-library update --version v0.5.0-beta" in notes
    assert "image-prompt-library rollback" in notes
    assert "137" in notes
    assert "AGPL-3.0-or-later" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()

def test_v06_release_notes_describe_generation_workflow_and_attachment_edits_beta():
    notes_path = ROOT / "docs" / "releases" / "v0.6.0-beta.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.6.0-beta" in notes
    assert "Generation Workflow & Attachment Edits" in notes
    assert "Online Read Only Demo" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.6/" in notes
    assert "first-run UI language" in notes
    assert "attachment" in notes
    assert "image edit" in notes
    assert "aspect ratio `Auto`" in notes
    assert "Save-as-new author" in notes
    assert "Account Management" in notes
    assert "image-prompt-library update --version v0.6.0-beta" in notes
    assert "image-prompt-library rollback" in notes
    assert "166" in notes
    assert "AGPL-3.0-or-later" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()


def test_v061_release_notes_describe_save_as_new_metadata_and_image_actions_beta():
    notes_path = ROOT / "docs" / "releases" / "v0.6.1-beta.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.6.1-beta" in notes
    assert "Save-as-new Metadata & Image Actions" in notes
    assert "Online Read Only Demo" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.6/" in notes
    assert "comma-separated" in notes
    assert "Collection suggestions" in notes
    assert "Source Language" in notes
    assert "ENG`, `繁中`, and `簡中`" in notes
    assert "notes for new generated items to empty" in notes
    assert "original image" in notes
    assert "Download actions" in notes
    assert "image-prompt-library update --version v0.6.1-beta" in notes
    assert "image-prompt-library rollback" in notes
    assert "168" in notes
    assert "AGPL-3.0-or-later" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()

def test_v071_release_notes_describe_queue_recovery_and_search_sort_beta():
    notes_path = ROOT / "docs" / "releases" / "v0.7.1-beta.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.7.1-beta" in notes
    assert "Queue Recovery" in notes
    assert "sort:updated" in notes
    assert "sort:created" in notes
    assert "sort:title" in notes
    assert "Cancel" in notes
    assert "interrupted by backend restart" in notes
    assert "No database schema change" in notes
    assert "image-prompt-library update --version v0.7.1-beta" in notes
    assert "image-prompt-library rollback" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()


def test_v074_release_notes_describe_reference_aware_queue_review_beta():
    notes_path = ROOT / "docs" / "releases" / "v0.7.4-beta.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.7.4-beta" in notes
    assert "Reference-Aware Queue Review" in notes
    assert "Used as ref" in notes
    assert "source_result_path" in notes
    assert "standalone generation panel" in notes
    assert "more than the most recent 50 jobs" in notes
    assert "Quick discard" in notes
    assert "No database schema change" in notes
    assert "image-prompt-library update --version v0.7.4-beta" in notes
    assert "image-prompt-library rollback" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()


def test_v073_release_notes_describe_safer_queue_recovery_beta():
    notes_path = ROOT / "docs" / "releases" / "v0.7.3-beta.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.7.3-beta" in notes
    assert "Safer Queue Recovery" in notes
    assert "Failed generation jobs can only be retried once" in notes
    assert "Already-retried failed jobs" in notes
    assert "Stale running jobs" in notes
    assert "retried_by_generation_job_id" in notes
    assert "retry_of_generation_job_id" in notes
    assert "failed_retry" in notes
    assert "stale_running_marked_failed" in notes
    assert "exclude developer/maintenance tooling" in notes
    assert "No database schema change" in notes
    assert "image-prompt-library update --version v0.7.3-beta" in notes
    assert "image-prompt-library rollback" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()


def test_v062_release_notes_describe_update_reliability_fixes_beta():
    notes_path = ROOT / "docs" / "releases" / "v0.6.2-beta.md"
    assert notes_path.exists()
    notes = notes_path.read_text()

    assert "# Image Prompt Library v0.6.2-beta" in notes
    assert "Update Reliability Fixes" in notes
    assert "Online Read Only Demo" in notes
    assert "https://eddietyp.github.io/image-prompt-library/v0.6/" in notes
    assert "browser-triggered app updates" in notes
    assert "macOS launchd" in notes
    assert "runtime Python" in notes
    assert "CLI `image-prompt-library update`" in notes
    assert "non-default service label" in notes
    assert "No database schema change" in notes
    assert "image-prompt-library update --version v0.6.2-beta" in notes
    assert "image-prompt-library rollback" in notes
    assert "171" in notes
    assert "AGPL-3.0-or-later" in notes

    assert "/Users/" not in notes
    assert ".local-work" not in notes
    assert "OpenNana" not in notes
    assert "token" not in notes.lower()
    assert "secret" not in notes.lower()
