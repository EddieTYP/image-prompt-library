from __future__ import annotations

import re


_SENSITIVE_STRUCTURED_KEYS = {
    "account_id",
    "access_token",
    "auth",
    "authentication",
    "api_key",
    "api_token",
    "authorization",
    "authorization_code",
    "bearer",
    "client_id",
    "client_secret",
    "code_verifier",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "device_auth_id",
    "header",
    "headers",
    "http_header",
    "http_headers",
    "id_token",
    "oauth",
    "password",
    "refresh_token",
    "secret",
    "session_id",
    "session_token",
    "token",
    "tokens",
    "user_code",
    "jwt",
    "private_key",
    "providers",
}

_SAFE_STRUCTURED_KEYS = {
    "auth_mode",
    "header_style",
    "input_tokens",
    "max_tokens",
    "output_tokens",
    "token_budget",
    "token_count",
    "total_tokens",
}

_WRAPPER_SUFFIXES = (
    "budget",
    "count",
    "credential",
    "credentials",
    "data",
    "header",
    "length",
    "limit",
    "mode",
    "name",
    "size",
    "string",
    "style",
    "type",
    "value",
)

_EMBEDDED_CREDENTIAL_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
)
_EMBEDDED_ASSIGNMENT_RE = re.compile(
    r"(?=(?:^|[?&,\s{\[\"'])"
    r"(?:\\?[\"'])?([A-Za-z][A-Za-z0-9_-]{0,63})(?:\\?[\"'])?"
    r"\s*[:=]\s*(?:\\?[\"'])?[^\s,;&}\]\"']+)",
    re.IGNORECASE,
)


def _normalize_structured_key(key: object) -> tuple[str, str]:
    raw_key = str(key).strip()
    raw_key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", raw_key)
    raw_key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw_key)
    normalized_key = re.sub(r"[^a-z0-9]+", "_", raw_key.lower()).strip("_")
    return normalized_key, normalized_key.replace("_", "")


def normalize_structured_key(key: object) -> str:
    return _normalize_structured_key(key)[0]


def _is_sensitive_structured_key(key: object) -> bool:
    normalized_key, compact_key = _normalize_structured_key(key)
    if normalized_key in _SAFE_STRUCTURED_KEYS:
        return False
    if normalized_key in _SENSITIVE_STRUCTURED_KEYS:
        return True
    padded_key = f"_{normalized_key}_"
    if any(f"_{sensitive_key}_" in padded_key for sensitive_key in _SENSITIVE_STRUCTURED_KEYS):
        return True
    sensitive_compact_keys = {key.replace("_", "") for key in _SENSITIVE_STRUCTURED_KEYS}
    variants = {compact_key}
    changed = True
    while changed:
        changed = False
        for variant in tuple(variants):
            for suffix in _WRAPPER_SUFFIXES:
                if variant.endswith(suffix) and len(variant) > len(suffix):
                    stripped = variant[: -len(suffix)]
                    if stripped not in variants:
                        variants.add(stripped)
                        changed = True
    return any(
        variant == sensitive_key or variant.endswith(sensitive_key)
        for variant in variants
        for sensitive_key in sensitive_compact_keys
    )


def contains_embedded_credential(value: str) -> bool:
    if any(pattern.search(value) for pattern in _EMBEDDED_CREDENTIAL_PATTERNS):
        return True
    return any(_is_sensitive_structured_key(match.group(1)) for match in _EMBEDDED_ASSIGNMENT_RE.finditer(value))


def _sanitize_structured_value(value, *, redact_image_data: bool):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            normalized_key, compact_key = _normalize_structured_key(key)
            if _is_sensitive_structured_key(key):
                continue
            if redact_image_data and (
                normalized_key in {"data_url", "image_url"}
                or compact_key.endswith(("dataurl", "imageurl"))
            ):
                continue
            sanitized[key] = _sanitize_structured_value(item, redact_image_data=redact_image_data)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_structured_value(item, redact_image_data=redact_image_data) for item in value]
    if isinstance(value, str):
        if redact_image_data and value.lstrip().lower().startswith("data:image/"):
            return "[redacted image data]"
        if contains_embedded_credential(value):
            return "[redacted credential data]"
    return value


def sanitize_structured_credentials(value: object, *, redact_image_data: bool = False) -> dict:
    sanitized = _sanitize_structured_value(value, redact_image_data=redact_image_data)
    return sanitized if isinstance(sanitized, dict) else {}
