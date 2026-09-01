from __future__ import annotations

import base64
import binascii
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

import httpx
from PIL import Image, UnidentifiedImageError

from backend.config import APP_VERSION, resolve_config_path, resolve_grok_auth_path, validate_app_owned_paths
from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository, resolve_generation_input_image_path
from backend.services.image_store import MAX_IMAGE_PIXELS
from backend.services.openai_codex_native import CodexNativeTemporaryError, normalize_title_suggestion, parse_retry_after_seconds

PROVIDER_ID = "xai_grok_oauth"
AUTH_MODE = "grok_oauth_device"
DISPLAY_NAME = "Grok OAuth · Experimental"
DEFAULT_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
AUTH_ISSUER = "https://auth.x.ai"
DEVICE_CODE_URL = f"{AUTH_ISSUER}/oauth2/device/code"
TOKEN_URL = f"{AUTH_ISSUER}/oauth2/token"
IMAGE_GENERATION_URL = "https://api.x.ai/v1/images/generations"
IMAGE_EDIT_URL = "https://api.x.ai/v1/images/edits"
RESPONSES_URL = "https://api.x.ai/v1/responses"
IMAGE_MODEL = "grok-imagine-image-2.0"
TITLE_MODEL = "grok-4.6"
SCOPES = (
    "openid",
    "profile",
    "email",
    "offline_access",
    "grok-cli:access",
    "api:access",
    "conversations:read",
    "conversations:write",
    "workspaces:read",
    "workspaces:write",
)
SUPPORTED_ASPECT_RATIOS = {"auto", "1:1", "3:4", "9:16", "4:3", "16:9"}
SUPPORTED_QUALITIES = {"low", "medium"}
SUPPORTED_RESOLUTIONS = {"1k", "2k"}
DEFAULT_QUALITY = "medium"
DEFAULT_RESOLUTION = "1k"
MAX_INPUT_IMAGES = 3

_refresh_lock = Lock()


class GrokOAuthError(RuntimeError):
    pass


class GrokOAuthTemporaryError(GrokOAuthError):
    pass


class GrokOAuthRequestError(GrokOAuthError):
    pass


class GrokOAuthRateLimitError(GrokOAuthError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


def _data_url_from_bytes(data: bytes, *, mime_type: str = "image/png") -> str:
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def _validate_input_image_bytes(data: bytes) -> None:
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise GrokOAuthError(f"Grok edit input image is too large: {width}x{height}")
            image.verify()
    except GrokOAuthError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise GrokOAuthError("Grok edit input contains invalid image data") from exc


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    header, _, encoded = data_url.partition(",")
    if not header.startswith("data:image/") or not encoded:
        raise GrokOAuthError("Grok edit input must be a data URL image")
    mime_type = header.removeprefix("data:").split(";", 1)[0] or "image/png"
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise GrokOAuthError("Grok edit input contains invalid image data") from exc
    _validate_input_image_bytes(data)
    return data, mime_type


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _client_id_from_config() -> str | None:
    path = resolve_config_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    providers = payload.get("providers") if isinstance(payload, dict) else None
    provider_config = providers.get(PROVIDER_ID) if isinstance(providers, dict) else None
    if not isinstance(provider_config, dict):
        return None
    client_id = str(provider_config.get("client_id", "") or "").strip()
    return client_id or None


def configured_client_id() -> str:
    return (
        os.environ.get("IMAGE_PROMPT_LIBRARY_GROK_CLIENT_ID", "").strip()
        or _client_id_from_config()
        or DEFAULT_CLIENT_ID
    )


def _response_json(response: httpx.Response, context: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise GrokOAuthError(f"{context} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise GrokOAuthError(f"{context} returned an invalid response shape")
    return payload


def _int_value(payload: dict[str, Any], key: str, default: int, context: str) -> int:
    try:
        raw_value = payload.get(key, default)
        return int(default if raw_value is None or raw_value == "" else raw_value)
    except (TypeError, ValueError) as exc:
        raise GrokOAuthError(f"{context} returned invalid {key}") from exc


def _oauth_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": f"ImagePromptLibrary/{APP_VERSION}",
        "x-grok-client-version": APP_VERSION,
        "x-grok-client-surface": "Ui",
    }


def _parse_expires_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class GrokOAuthAuthStore:
    """App-owned xAI OAuth tokens stored separately from the image library and Codex OAuth."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path).expanduser() if path is not None else resolve_grok_auth_path()

    def save_tokens(self, tokens: dict[str, Any], *, previous_refresh_token: str | None = None) -> None:
        access_token = str(tokens.get("access_token", "") or "").strip()
        refresh_token = str(tokens.get("refresh_token", "") or previous_refresh_token or "").strip()
        if not access_token or not refresh_token:
            raise GrokOAuthError("Grok OAuth requires access_token and refresh_token")
        expires_in = max(0, _int_value(tokens, "expires_in", 3600, "Grok OAuth token response"))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        payload = {
            "provider": PROVIDER_ID,
            "auth_mode": AUTH_MODE,
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            },
            "last_refresh": _utc_now(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        fd, temp_name = tempfile.mkstemp(prefix="grok-auth-", suffix=".tmp", dir=self.path.parent)
        temp_path = Path(temp_name)
        handle = None
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            handle = os.fdopen(fd, "w", encoding="utf-8")
            json.dump(payload, handle, indent=2)
            handle.close()
            handle = None
            os.replace(temp_path, self.path)
            self.path.chmod(0o600)
        except Exception:
            if handle is not None:
                handle.close()
            temp_path.unlink(missing_ok=True)
            raise

    def _read_raw_tokens(self) -> dict[str, str]:
        if not self.path.is_file():
            raise GrokOAuthError("No Grok OAuth credentials saved")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GrokOAuthError("Grok OAuth credential store is invalid") from exc
        tokens = payload.get("tokens") if isinstance(payload, dict) else None
        if not isinstance(tokens, dict):
            raise GrokOAuthError("Grok OAuth credential store is missing tokens")
        access_token = str(tokens.get("access_token", "") or "").strip()
        refresh_token = str(tokens.get("refresh_token", "") or "").strip()
        expires_at = str(tokens.get("expires_at", "") or "").strip()
        if not access_token or not refresh_token or _parse_expires_at(expires_at) is None:
            raise GrokOAuthError("Grok OAuth credential store has incomplete tokens")
        return {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}

    @staticmethod
    def _expires_soon(tokens: dict[str, str], skew_seconds: int = 300) -> bool:
        expires_at = _parse_expires_at(tokens.get("expires_at"))
        return expires_at is None or expires_at <= datetime.now(timezone.utc) + timedelta(seconds=skew_seconds)

    def read_tokens(self, http_client: httpx.Client | None = None) -> dict[str, str]:
        tokens = self._read_raw_tokens()
        if not self._expires_soon(tokens):
            return tokens
        with _refresh_lock:
            tokens = self._read_raw_tokens()
            if not self._expires_soon(tokens):
                return tokens
            return self.refresh_tokens(tokens["refresh_token"], http_client=http_client)

    def refresh_tokens(self, refresh_token: str, http_client: httpx.Client | None = None) -> dict[str, str]:
        close_client = http_client is None
        client = http_client or httpx.Client(timeout=httpx.Timeout(15.0))
        try:
            try:
                response = client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": configured_client_id(),
                    },
                    headers=_oauth_headers(),
                )
            except httpx.HTTPError as exc:
                raise GrokOAuthTemporaryError("Grok OAuth refresh is temporarily unavailable") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code == 408 or response.status_code >= 500:
            raise GrokOAuthTemporaryError("Grok OAuth refresh is temporarily unavailable")
        if response.status_code != 200:
            raise GrokOAuthError("Grok OAuth session has expired. Connect again.")
        payload = _response_json(response, "Grok OAuth refresh")
        self.save_tokens(payload, previous_refresh_token=refresh_token)
        return self._read_raw_tokens()

    def delete_tokens(self) -> None:
        self.path.unlink(missing_ok=True)

    def status(self) -> dict[str, Any]:
        token_present = False
        saved_credentials_broken = False
        temporary_unavailable = False
        try:
            self._read_raw_tokens()
            token_present = True
            self.read_tokens()
        except GrokOAuthTemporaryError:
            temporary_unavailable = True
        except GrokOAuthError:
            saved_credentials_broken = self.path.is_file()
            token_present = False
        available = token_present and not temporary_unavailable
        if available:
            status = "ready"
            message = None
            state = "connected"
        elif temporary_unavailable:
            status = "unavailable"
            message = "Grok OAuth is temporarily unavailable. Try again shortly."
            state = "connected"
        elif saved_credentials_broken:
            status = "auth_error"
            message = "Grok OAuth needs attention before generating."
            state = "not_connected"
        else:
            status = "login_required"
            message = "Connect Grok OAuth before generating."
            state = "not_connected"
        return {
            "provider": PROVIDER_ID,
            "display_name": DISPLAY_NAME,
            "auth_mode": AUTH_MODE,
            "optional": True,
            "configured": True,
            "authenticated": token_present,
            "available": available,
            "state": state,
            "reason": None if available else "not_authenticated",
            "status": status,
            "message": message,
            "can_generate": available,
            "features": {
                "text_to_image": available,
                "text_reference_to_image": available,
                "image_edit": available,
                "title_suggestion": available,
            },
            "max_input_images": MAX_INPUT_IMAGES,
            "image_models": [IMAGE_MODEL],
            "default_image_model": IMAGE_MODEL,
            "token_present": token_present,
            "auth_store_path": str(self.path),
        }


class GrokDeviceCodeFlow:
    def __init__(self, auth_store: GrokOAuthAuthStore | None = None, http_client: httpx.Client | None = None):
        self.auth_store = auth_store or GrokOAuthAuthStore()
        self.http_client = http_client

    def _client(self) -> httpx.Client:
        return self.http_client or httpx.Client(timeout=httpx.Timeout(15.0))

    def start(self) -> dict[str, Any]:
        close_client = self.http_client is None
        client = self._client()
        try:
            try:
                response = client.post(
                    DEVICE_CODE_URL,
                    data={
                        "client_id": configured_client_id(),
                        "scope": " ".join(SCOPES),
                        "referrer": "image-prompt-library",
                    },
                    headers=_oauth_headers(),
                )
            except httpx.HTTPError as exc:
                raise GrokOAuthTemporaryError("Grok device login is temporarily unavailable") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code == 408 or response.status_code >= 500:
            raise GrokOAuthTemporaryError("Grok device login is temporarily unavailable")
        if response.status_code != 200:
            raise GrokOAuthError(f"Grok device login returned status {response.status_code}")
        payload = _response_json(response, "Grok device login")
        device_code = str(payload.get("device_code", "") or "").strip()
        user_code = str(payload.get("user_code", "") or "").strip()
        verification_uri = str(payload.get("verification_uri", "") or "").strip()
        verification_uri_complete = str(payload.get("verification_uri_complete", "") or "").strip()
        if not device_code or not user_code or not verification_uri.startswith("https://"):
            raise GrokOAuthError("Grok device login response is incomplete")
        return {
            "provider": PROVIDER_ID,
            "auth_mode": AUTH_MODE,
            "device_code": device_code,
            "user_code": user_code,
            "verification_url": verification_uri_complete or verification_uri,
            "verification_uri": verification_uri,
            "verification_uri_complete": verification_uri_complete or None,
            "interval": max(3, _int_value(payload, "interval", 5, "Grok device login")),
            "expires_in": max(60, _int_value(payload, "expires_in", 900, "Grok device login")),
        }

    def poll_device_authorization(self, device_code: str) -> dict[str, Any]:
        code = str(device_code or "").strip()
        if not code:
            raise GrokOAuthError("device_code is required")
        close_client = self.http_client is None
        client = self._client()
        try:
            try:
                response = client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code": code,
                        "client_id": configured_client_id(),
                    },
                    headers=_oauth_headers(),
                )
            except httpx.HTTPError as exc:
                raise GrokOAuthTemporaryError("Grok device login check is temporarily unavailable") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code == 200:
            payload = _response_json(response, "Grok device login check")
            self.auth_store.save_tokens(payload)
            status = self.auth_store.status()
            status["status"] = "approved"
            return status
        error = ""
        try:
            payload = response.json()
            error = str(payload.get("error", "") or "").strip() if isinstance(payload, dict) else ""
        except ValueError:
            pass
        if error in {"authorization_pending", "slow_down"}:
            return {"provider": PROVIDER_ID, "auth_mode": AUTH_MODE, "status": "pending"}
        if error == "access_denied":
            raise GrokOAuthError("Grok device login was denied")
        if error == "expired_token":
            raise GrokOAuthError("Grok device login expired. Start again.")
        if response.status_code == 408 or response.status_code >= 500:
            raise GrokOAuthTemporaryError("Grok device login check is temporarily unavailable")
        raise GrokOAuthError(f"Grok device login check returned status {response.status_code}")


class XaiGrokOAuthProvider:
    def __init__(
        self,
        auth_store: GrokOAuthAuthStore | None = None,
        timeout: float = 300.0,
        http_client: httpx.Client | None = None,
    ):
        self.auth_store = auth_store or GrokOAuthAuthStore()
        self.timeout = timeout
        self.http_client = http_client

    def suggest_title(self, library_path: Path | str, prompt_text: str) -> str:
        try:
            validate_app_owned_paths(library_path)
        except ValueError as exc:
            raise GrokOAuthError(
                "Provider credentials or library storage paths are unsafe. Move app-owned credentials outside the active library and restart."
            ) from exc
        prompt = str(prompt_text or "").strip()
        if not prompt:
            raise GrokOAuthError("Prompt text is required")
        tokens = self.auth_store.read_tokens(http_client=self.http_client)
        payload = {
            "model": TITLE_MODEL,
            "store": False,
            "reasoning": {"effort": "low"},
            "max_output_tokens": 128,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Suggest one concise library title for the image prompt. "
                        "Use the same language as the prompt. Return only the title, without quotes, labels, markdown, or commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=httpx.Timeout(min(self.timeout, 30.0)))
        try:
            try:
                response = client.post(
                    RESPONSES_URL,
                    headers={
                        "Authorization": f"Bearer {tokens['access_token']}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": f"ImagePromptLibrary/{APP_VERSION}",
                    },
                    json=payload,
                )
            except httpx.HTTPError as exc:
                raise GrokOAuthTemporaryError("Grok title suggestion is temporarily unavailable") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code == 429:
            raise GrokOAuthRateLimitError(
                "Grok title suggestion is temporarily rate limited.",
                retry_after_seconds=parse_retry_after_seconds(response.headers.get("Retry-After")),
            )
        if response.status_code in {401, 403}:
            raise GrokOAuthRequestError("Grok title access is unavailable for this account")
        if response.status_code == 408 or response.status_code >= 500:
            raise GrokOAuthTemporaryError("Grok title suggestion is temporarily unavailable")
        if response.status_code != 200:
            raise GrokOAuthRequestError(f"Grok title suggestion returned status {response.status_code}")
        try:
            response_payload = _response_json(response, "Grok title suggestion")
        except GrokOAuthError as exc:
            raise GrokOAuthRequestError("Grok title suggestion returned an invalid response") from exc
        output = response_payload.get("output")
        if not isinstance(output, list):
            raise GrokOAuthRequestError("Grok title suggestion returned an invalid response")
        output_text_parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            output_text_parts.extend(
                str(content.get("text", ""))
                for content in content_items
                if isinstance(content, dict) and content.get("type") == "output_text"
            )
        output_text = "".join(output_text_parts)
        try:
            return normalize_title_suggestion(output_text)
        except CodexNativeTemporaryError as exc:
            raise GrokOAuthTemporaryError("Grok response contained no title suggestion") from exc

    def run_job(self, library_path: Path | str, job_id: str):
        try:
            validate_app_owned_paths(library_path)
        except ValueError as exc:
            raise GrokOAuthError(
                "Provider credentials or library storage paths are unsafe. Move app-owned credentials outside the active library and restart."
            ) from exc
        repo = GenerationJobRepository(library_path)
        job = repo.get_job(job_id)
        if job.provider != PROVIDER_ID:
            raise GenerationJobConflict(f"Generation job provider must be {PROVIDER_ID}")
        if job.status == "succeeded":
            return job
        if job.status == "cancelled":
            raise GenerationJobConflict("Generation job is cancelled")
        if job.status not in {"queued", "failed"}:
            raise GenerationJobConflict("Generation job must be queued or failed before run")
        prompt = (job.edited_prompt_text or job.prompt_text or "").strip()
        if not prompt:
            raise GenerationJobConflict("Generation prompt is required")
        parameters = job.parameters or {}
        aspect_ratio = str(parameters.get("requested_aspect_ratio") or "auto").strip().lower()
        if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
            aspect_ratio = "auto"
        quality = str(parameters.get("quality") or DEFAULT_QUALITY).strip().lower()
        if quality not in SUPPORTED_QUALITIES:
            quality = DEFAULT_QUALITY
        resolution = str(parameters.get("resolution") or DEFAULT_RESOLUTION).strip().lower()
        if resolution not in SUPPORTED_RESOLUTIONS:
            resolution = DEFAULT_RESOLUTION
        repo.mark_running(job_id)
        try:
            input_images = self._input_image_data_urls(job, Path(library_path))
            image_bytes = self._generate_image(
                prompt,
                aspect_ratio,
                quality=quality,
                resolution=resolution,
                input_images=input_images,
            )
            filename = self._image_filename(image_bytes)
            return repo.stage_result(job_id, image_bytes, filename, {
                "provider": PROVIDER_ID,
                "auth_mode": AUTH_MODE,
                "model": IMAGE_MODEL,
                "image_model": IMAGE_MODEL,
                "requested_aspect_ratio": aspect_ratio,
                "quality": quality,
                "resolution": resolution,
                "source_job_id": job_id,
                "mode": "image_edit" if input_images else "text_to_image",
                "input_image_count": len(input_images),
            })
        except GrokOAuthRateLimitError as exc:
            failed = repo.mark_failed(job_id, str(exc), exc.retry_after_seconds)
            repo.record_provider_rate_limit(PROVIDER_ID, exc.retry_after_seconds)
            raise GrokOAuthRateLimitError(
                failed.error or "Grok image generation is temporarily limited",
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        except Exception as exc:
            failed = repo.mark_failed(job_id, str(exc))
            raise GrokOAuthError(failed.error or "Grok image generation failed") from exc

    def _input_image_data_urls(self, job, library_path: Path) -> list[dict[str, str]]:
        raw_images = job.parameters.get("input_images") if isinstance(job.parameters, dict) else None
        if not isinstance(raw_images, list):
            return []
        if len(raw_images) > MAX_INPUT_IMAGES:
            raise GrokOAuthError(f"Grok image editing supports up to {MAX_INPUT_IMAGES} input images")
        input_images: list[dict[str, str]] = []
        repo = GenerationJobRepository(library_path)
        for raw in raw_images:
            if not isinstance(raw, dict):
                continue
            source = str(raw.get("source") or "uploaded")
            image_id = raw.get("image_id")
            if source == "library" and isinstance(image_id, str) and image_id:
                try:
                    result_path = raw.get("result_path")
                    if isinstance(result_path, str) and result_path:
                        image_path, mime_type = resolve_generation_input_image_path(
                            library_path,
                            result_path,
                            allowed_roots={"generation-references"},
                        )
                    else:
                        _, image_path, mime_type = repo.resolve_library_reference(image_id)
                except GenerationJobConflict as exc:
                    raise GrokOAuthError(str(exc)) from exc
                data = image_path.read_bytes()
                _validate_input_image_bytes(data)
                input_images.append({"type": "image_url", "url": _data_url_from_bytes(data, mime_type=mime_type)})
                continue
            data_url = raw.get("data_url")
            if isinstance(data_url, str) and data_url:
                data, mime_type = _decode_data_url(data_url)
                input_images.append({"type": "image_url", "url": _data_url_from_bytes(data, mime_type=mime_type)})
                continue
            result_path = raw.get("result_path")
            if isinstance(result_path, str) and result_path:
                try:
                    image_path, mime_type = resolve_generation_input_image_path(library_path, result_path)
                except GenerationJobConflict as exc:
                    raise GrokOAuthError(str(exc)) from exc
                data = image_path.read_bytes()
                _validate_input_image_bytes(data)
                input_images.append({"type": "image_url", "url": _data_url_from_bytes(data, mime_type=mime_type)})
        return input_images

    def _generate_image(
        self,
        prompt: str,
        aspect_ratio: str,
        *,
        quality: str,
        resolution: str,
        input_images: list[dict[str, str]],
    ) -> bytes:
        tokens = self.auth_store.read_tokens(http_client=self.http_client)
        payload = {
            "model": IMAGE_MODEL,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "quality": quality,
            "resolution": resolution,
            "response_format": "b64_json",
        }
        endpoint = IMAGE_GENERATION_URL
        if input_images:
            endpoint = IMAGE_EDIT_URL
            payload["image" if len(input_images) == 1 else "images"] = input_images[0] if len(input_images) == 1 else input_images
        else:
            payload["n"] = 1
        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=httpx.Timeout(self.timeout))
        try:
            try:
                response = client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {tokens['access_token']}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": f"ImagePromptLibrary/{APP_VERSION}",
                    },
                    json=payload,
                )
            except httpx.HTTPError as exc:
                raise GrokOAuthTemporaryError("Grok image generation is temporarily unavailable") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code == 429:
            raise GrokOAuthRateLimitError(
                "Grok image generation is unavailable for this account or temporarily limited.",
                retry_after_seconds=parse_retry_after_seconds(response.headers.get("Retry-After")),
            )
        if response.status_code in {401, 403}:
            raise GrokOAuthError("Grok image access is unavailable for this account. Reconnect or check the account plan.")
        if response.status_code == 408 or response.status_code >= 500:
            raise GrokOAuthTemporaryError("Grok image generation is temporarily unavailable")
        if response.status_code != 200:
            raise GrokOAuthRequestError(f"Grok image generation returned status {response.status_code}")
        payload = _response_json(response, "Grok image generation")
        data = payload.get("data")
        first = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else None
        encoded = str(first.get("b64_json", "") or "").strip() if first else ""
        if not encoded:
            raise GrokOAuthError("Grok image generation returned no image")
        try:
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise GrokOAuthError("Grok image generation returned invalid image data") from exc

    @staticmethod
    def _image_filename(data: bytes) -> str:
        try:
            with Image.open(BytesIO(data)) as image:
                suffix = {"JPEG": ".jpg", "WEBP": ".webp"}.get(image.format, ".png")
        except OSError as exc:
            raise GrokOAuthError("Grok image generation returned invalid image data") from exc
        return f"xai-grok-imagine{suffix}"
