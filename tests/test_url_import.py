import json

import pytest

from backend.services.url_import import UrlImportError, preview_url_import


def response(body: str, content_type: str = "text/html; charset=utf-8"):
    return "https://example.com/post", {"content-type": content_type}, body.encode()


def test_generic_url_preview_extracts_metadata_without_persisting(tmp_path):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    import backend.routers.import_drafts as router

    html = '<html><head><meta property="og:title" content="Poster"><meta property="og:site_name" content="Example"><meta property="og:description" content="A cinematic red poster"></head></html>'
    original = router.preview_url_import
    router.preview_url_import = lambda url: preview_url_import(url, lambda _: response(html))
    try:
        client = TestClient(create_app(library_path=tmp_path / "library"))
        preview = client.post("/api/import-drafts/url-preview", json={"url": "https://example.com/post"})
        assert preview.status_code == 200
        assert preview.json()["prompts"][0]["text"] == "A cinematic red poster"
        assert client.get("/api/import-drafts").json()["total"] == 0
    finally:
        router.preview_url_import = original


def test_x_preview_uses_official_oembed_text():
    payload = {"author_name": "Artist", "html": '<blockquote><p>Neon city &amp; rain</p></blockquote>'}
    preview = preview_url_import(
        "https://x.com/artist/status/123",
        lambda url: response(json.dumps(payload), "application/json"),
    )
    assert preview.source_type == "x"
    assert preview.author == "Artist"
    assert preview.prompts[0].text == "Neon city & rain"


def test_threads_without_metadata_returns_manual_review_warning():
    preview = preview_url_import(
        "https://www.threads.net/@artist/post/example",
        lambda _: ("https://www.threads.net/@artist/post/example", {"content-type": "text/html"}, b"<html><title>Threads post</title></html>"),
    )
    assert preview.source_type == "threads"
    assert preview.prompts == []
    assert any("manually" in warning for warning in preview.warnings)


def test_threads_net_redirect_to_threads_com_stays_a_threads_import():
    preview = preview_url_import(
        "https://www.threads.net/@artist/post/example",
        lambda _: ("https://www.threads.com/@artist/post/example", {"content-type": "text/html"}, b"<html><title>Threads post</title></html>"),
    )
    assert preview.source_type == "threads"
    assert preview.source_name == "Threads"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.com", "https://example.com:8443", "https://example.com:80"])
def test_fetch_rejects_unsafe_url_shapes(url):
    from backend.services.url_import import _request_once

    with pytest.raises(UrlImportError):
        _request_once(url)


def test_fetch_rejects_host_that_resolves_to_private_address(monkeypatch):
    from backend.services.url_import import _request_once

    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(UrlImportError, match="private"):
        _request_once("http://example.com")
