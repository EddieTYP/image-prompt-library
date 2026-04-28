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
