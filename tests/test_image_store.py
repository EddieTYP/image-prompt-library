from io import BytesIO
from pathlib import Path
from PIL import Image
from backend.services.image_store import store_image


def png_bytes(size=(320, 200), color=(120, 40, 220)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_store_image_creates_original_thumb_and_preview(tmp_path: Path):
    record = store_image(tmp_path / "library", png_bytes(), "sample.png")
    assert record.width == 320
    assert record.height == 200
    assert len(record.file_sha256) == 64
    assert (tmp_path / "library" / record.original_path).exists()
    assert (tmp_path / "library" / record.thumb_path).exists()
    assert (tmp_path / "library" / record.preview_path).exists()
    with Image.open(tmp_path / "library" / record.thumb_path) as thumb:
        assert max(thumb.size) <= 420


def test_store_image_rejects_too_many_pixels(tmp_path: Path):
    data = png_bytes(size=(5000, 5000))
    try:
        store_image(tmp_path / "library", data, "huge.png")
    except ValueError as exc:
        assert "too large" in str(exc)
    else:
        raise AssertionError("expected oversized image to be rejected")
