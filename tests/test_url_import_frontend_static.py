from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_detail_modal_displays_imported_original_language_prompt():
    detail = (ROOT / "frontend" / "src" / "components" / "ItemDetailModal.tsx").read_text(encoding="utf-8")

    assert "original: 'ORIGIN'" in detail
    assert "displayPromptLanguages.map" in detail
    assert "return originalLanguage || 'en'" in detail
