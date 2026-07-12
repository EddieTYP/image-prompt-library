from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import quote, urlencode, urljoin, urlsplit

from backend.schemas import ImportDraftCreate, PromptIn

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT_SECONDS = 8
USER_AGENT = "ImagePromptLibrary/0.8 URL Import"


class UrlImportError(ValueError):
    pass


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.json_ld: list[str] = []
        self._in_title = False
        self._in_json_ld = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        elif tag.lower() == "script" and values.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False
        elif tag.lower() == "script" and self._in_json_ld:
            self._in_json_ld = False
            self.json_ld.append("".join(self._script_parts))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_json_ld:
            self._script_parts.append(data)


class _OEmbedTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._paragraph_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "p":
            self._paragraph_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "p" and self._paragraph_depth:
            self._paragraph_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._paragraph_depth:
            self.parts.append(data)


def _clean(value: str | None) -> str:
    return " ".join((value or "").split())


def _public_addresses(hostname: str, port: int) -> list[str]:
    try:
        resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(info[4][0] for info in resolved))
    except socket.gaierror as exc:
        raise UrlImportError("Could not resolve the URL host.") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise UrlImportError("Local and private network URLs are not allowed.")
    return addresses


def _request_once(url: str) -> tuple[int, dict[str, str], bytes]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise UrlImportError("Enter a public http or https URL.")
    expected_port = 443 if parsed.scheme == "https" else 80
    try:
        port = parsed.port or expected_port
    except ValueError as exc:
        raise UrlImportError("The URL contains an invalid port.") from exc
    if port != expected_port:
        raise UrlImportError("Only standard web ports are allowed.")
    hostname = parsed.hostname.encode("idna").decode("ascii")
    addresses = _public_addresses(hostname, port)
    target = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    if parsed.query:
        target += "?" + quote(parsed.query, safe="=&%:@!$'()*+,;/?-._~")
    last_error: OSError | None = None
    for address in addresses:
        sock: socket.socket | ssl.SSLSocket | None = None
        try:
            sock = socket.create_connection((address, port), TIMEOUT_SECONDS)
            if parsed.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=hostname)
            host_header = f"[{hostname}]" if ":" in hostname else hostname
            request = (
                f"GET {target} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: {USER_AGENT}\r\n"
                "Accept: text/html, application/json;q=0.8\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
            )
            sock.sendall(request.encode("ascii"))
            response = http.client.HTTPResponse(sock)
            response.begin()
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise UrlImportError("The page is too large to preview.")
            headers = {key.lower(): value for key, value in response.getheaders()}
            return response.status, headers, body
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            if sock is not None:
                sock.close()
    raise UrlImportError("Could not fetch the URL.") from last_error


def fetch_url(url: str) -> tuple[str, dict[str, str], bytes]:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        status, headers, body = _request_once(current)
        if status in {301, 302, 303, 307, 308}:
            location = headers.get("location")
            if not location:
                raise UrlImportError("The page returned an invalid redirect.")
            current = urljoin(current, location)
            continue
        if status < 200 or status >= 300:
            raise UrlImportError(f"The page returned HTTP {status}.")
        return current, headers, body
    raise UrlImportError("The page redirected too many times.")


def _json_ld_values(value: Any, keys: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and _clean(candidate):
                found.append(_clean(candidate))
        for child in value.values():
            found.extend(_json_ld_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            found.extend(_json_ld_values(child, keys))
    return found


def _decode(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    for part in content_type.split(";")[1:]:
        if part.strip().lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip().strip('"')
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _generic_preview(source_url: str, final_url: str, headers: dict[str, str], body: bytes) -> ImportDraftCreate:
    content_type = headers.get("content-type", "").lower()
    if "html" not in content_type and not body.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise UrlImportError("The URL does not point to an HTML page.")
    parser = _MetadataParser()
    parser.feed(_decode(body, content_type))
    json_prompts: list[str] = []
    for raw in parser.json_ld:
        try:
            json_prompts.extend(_json_ld_values(json.loads(raw), ("text", "articleBody", "description")))
        except json.JSONDecodeError:
            continue
    prompt = next((value for value in json_prompts if value), "") or _clean(
        parser.meta.get("og:description") or parser.meta.get("twitter:description") or parser.meta.get("description")
    )
    host = urlsplit(final_url).hostname or urlsplit(source_url).hostname or "Imported page"
    title = _clean(
        parser.meta.get("og:title") or parser.meta.get("twitter:title") or "".join(parser.title_parts)
    ) or host
    site_name = _clean(parser.meta.get("og:site_name")) or host
    is_threads = host.lower() in {"threads.net", "www.threads.net", "threads.com", "www.threads.com"}
    warnings: list[str] = []
    if not prompt:
        warnings.append("No reusable prompt text was found. Paste the prompt manually before importing.")
    if is_threads:
        warnings.append("Threads metadata is best-effort and may require manual review.")
    return ImportDraftCreate(
        source_type="threads" if is_threads else "url",
        source_name="Threads" if is_threads else site_name,
        source_url=source_url,
        title=title,
        prompts=[PromptIn(language="original", text=prompt, is_primary=True, is_original=True)] if prompt else [],
        warnings=warnings,
        confidence=0.75 if prompt else 0.35,
    )


def _is_x_status(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    return (
        parsed.scheme in {"http", "https"}
        and host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
        and len(parts) >= 3
        and parts[-2] == "status"
        and parts[-1].isdigit()
    )


def _x_preview(source_url: str, fetcher: Callable[[str], tuple[str, dict[str, str], bytes]]) -> ImportDraftCreate:
    oembed_url = "https://publish.x.com/oembed?" + urlencode({"url": source_url, "omit_script": "true", "dnt": "true"})
    _, headers, body = fetcher(oembed_url)
    try:
        payload = json.loads(_decode(body, headers.get("content-type", "application/json")))
    except json.JSONDecodeError as exc:
        raise UrlImportError("X returned an invalid preview.") from exc
    parser = _OEmbedTextParser()
    parser.feed(str(payload.get("html") or ""))
    prompt = _clean("".join(parser.parts))
    if not prompt:
        raise UrlImportError("X did not return post text for this URL.")
    author = _clean(str(payload.get("author_name") or "")) or None
    return ImportDraftCreate(
        source_type="x",
        source_name="X",
        source_url=source_url,
        title=f"X post by {author}" if author else "X post",
        author=author,
        prompts=[PromptIn(language="original", text=prompt, is_primary=True, is_original=True)],
        confidence=0.9,
    )


def preview_url_import(
    url: str,
    fetcher: Callable[[str], tuple[str, dict[str, str], bytes]] = fetch_url,
) -> ImportDraftCreate:
    source_url = url.strip()
    if _is_x_status(source_url):
        return _x_preview(source_url, fetcher)
    final_url, headers, body = fetcher(source_url)
    return _generic_preview(source_url, final_url, headers, body)
