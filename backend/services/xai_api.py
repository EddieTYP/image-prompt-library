from __future__ import annotations

import base64
import binascii
import json
import os
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, UnidentifiedImageError

from backend.config import resolve_auth_path
from backend.services.generation_jobs import (
    GenerationJobConflict,
    GenerationJobRepository,
    resolve_generation_input_image_path,
    sanitize_generation_error,
)
from backend.services.image_store import MAX_IMAGE_PIXELS
from backend.services.openai_codex_native import parse_retry_after_seconds

PROVIDER_ID = "xai_api"
AUTH_MODE = "api_key_env"
DISPLAY_NAME = "xAI Grok Imagine"
MODEL = "grok-imagine-image-2.0"
BASE_URL = "https://api.x.ai/v1"
MAX_INPUT_IMAGES = 3
SUPPORTED_ASPECT_RATIOS = {"auto", "1:1", "3:4", "9:16", "4:3", "16:9"}
SUPPORTED_QUALITIES = {"low", "medium"}


class XAIAPIError(RuntimeError):
    pass


class XAIAPIAuthError(XAIAPIError):
    pass


class XAIAPIRateLimitError(XAIAPIError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class XAIAPITemporaryError(XAIAPIError):
    pass


class XAIAPIKeyStore:
    """App-owned xAI key store kept beside, but separate from, Codex OAuth tokens."""

    def __init__(self, path: Path | str | None = None):
        auth_path = resolve_auth_path()
        self.path = Path(path).expanduser() if path is not None else auth_path.with_name("xai-api-key.json")

    def save_key(self, api_key: str) -> None:
        key = str(api_key or "").strip()
        if len(key) < 8:
            raise XAIAPIAuthError("Enter a valid xAI API key")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        payload = json.dumps({"provider": PROVIDER_ID, "auth_mode": "api_key_local", "api_key": key}, indent=2)
        fd, temp_name = tempfile.mkstemp(prefix="xai-auth-", suffix=".tmp", dir=self.path.parent)
        temp_path = Path(temp_name)
        handle = None
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            handle = os.fdopen(fd, "w", encoding="utf-8")
            handle.write(payload)
            handle.close()
            handle = None
            os.replace(temp_path, self.path)
            self.path.chmod(0o600)
        except Exception:
            try:
                if handle is not None:
                    handle.close()
                temp_path.unlink(missing_ok=True)
            finally:
                raise

    def read_key(self) -> str:
        if not self.path.is_file():
            return ""
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return ""
        key = payload.get("api_key") if isinstance(payload, dict) else None
        return key.strip() if isinstance(key, str) else ""

    def delete_key(self) -> None:
        self.path.unlink(missing_ok=True)


def xai_api_key(key_store: XAIAPIKeyStore | None = None) -> str:
    environment_key = os.environ.get("XAI_API_KEY", "").strip()
    if environment_key:
        return environment_key
    return (key_store or XAIAPIKeyStore()).read_key()


def xai_status(key_store: XAIAPIKeyStore | None = None) -> dict[str, Any]:
    store = key_store or XAIAPIKeyStore()
    environment_managed = bool(os.environ.get("XAI_API_KEY", "").strip())
    local_key_present = bool(store.read_key())
    configured = environment_managed or local_key_present
    return {
        "provider": PROVIDER_ID,
        "display_name": DISPLAY_NAME,
        "auth_mode": AUTH_MODE if environment_managed else "api_key_local",
        "optional": True,
        "configured": configured,
        "authenticated": configured,
        "available": configured,
        "state": "available" if configured else "not_configured",
        "reason": None if configured else "missing_api_key",
        "status": "ready" if configured else "unavailable",
        "message": None if configured else "Add an xAI API key in Config before generating.",
        "can_generate": configured,
        "credential_source": "environment" if environment_managed else ("local_store" if local_key_present else None),
        "managed_by_environment": environment_managed,
        "key_present": configured,
        "features": {
            "text_to_image": configured,
            "text_reference_to_image": configured,
            "image_edit": configured,
        },
        "image_models": [MODEL],
        "default_image_model": MODEL,
        "quality_options": ["low", "medium"],
        "default_quality": "medium",
        "max_input_images": MAX_INPUT_IMAGES,
        "retention_days": 30,
        "supports_zero_data_retention": True,
    }


def _validate_input_image_bytes(data: bytes) -> None:
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise XAIAPIError(f"Generation edit input image is too large: {width}x{height}")
            image.verify()
    except XAIAPIError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise XAIAPIError("Generation edit input image contains invalid image data") from exc


def _decode_data_url(data_url: str) -> tuple[bytes, str]:
    header, _, encoded = data_url.partition(",")
    if not header.startswith("data:image/") or not encoded:
        raise XAIAPIError("Generation edit input image must be a data URL image")
    mime_type = header.removeprefix("data:").split(";", 1)[0] or "image/png"
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise XAIAPIError("Generation edit input image contains invalid image data") from exc
    _validate_input_image_bytes(data)
    return data, mime_type


def _data_url(data: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"


def _normalize_quality(value: Any) -> str:
    requested = str(value or "medium").strip().lower()
    return requested if requested in SUPPORTED_QUALITIES else "medium"


def _normalize_aspect_ratio(value: Any) -> str:
    requested = str(value or "auto").strip().lower()
    return requested if requested in SUPPORTED_ASPECT_RATIOS else "auto"


def _response_image(response: httpx.Response) -> tuple[bytes, str, bool]:
    try:
        payload = response.json()
        images = payload.get("data") if isinstance(payload, dict) else None
        first = images[0] if isinstance(images, list) and images else None
        encoded = first.get("b64_json") if isinstance(first, dict) else None
        mime_type = str(first.get("mime_type") or "image/jpeg") if isinstance(first, dict) else "image/jpeg"
        if not isinstance(encoded, str) or not encoded:
            raise ValueError
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError, TypeError, AttributeError) as exc:
        raise XAIAPIError("xAI returned invalid image data") from exc
    return image_bytes, mime_type, response.headers.get("x-zero-data-retention", "").lower() == "true"


class XAIAPIProvider:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 120.0,
        http_client: httpx.Client | None = None,
        base_url: str = BASE_URL,
    ):
        if api_key is None:
            status = xai_status()
            self.api_key = xai_api_key()
            self.auth_mode = str(status["auth_mode"])
        else:
            self.api_key = api_key.strip()
            self.auth_mode = AUTH_MODE
        self.timeout = timeout
        self.http_client = http_client
        self.base_url = base_url.rstrip("/")

    def run_job(self, library_path: Path | str, job_id: str):
        repo = GenerationJobRepository(library_path)
        job = repo.get_job(job_id)
        if job.provider != PROVIDER_ID:
            raise GenerationJobConflict(f"Generation job provider must be {PROVIDER_ID}")
        if job.status == "succeeded":
            return job
        if job.status == "running":
            deadline = time.time() + min(self.timeout, 30.0)
            while time.time() < deadline:
                current = repo.get_job(job_id)
                if current.status != "running":
                    if current.status == "succeeded":
                        return current
                    if current.status == "cancelled":
                        raise GenerationJobConflict("Generation job is cancelled")
                    if current.status == "failed":
                        raise XAIAPIError(sanitize_generation_error(current.error or "Generation job failed"))
                    job = current
                    break
                time.sleep(0.05)
            else:
                return repo.get_job(job_id)
        if job.status == "cancelled":
            raise GenerationJobConflict("Generation job is cancelled")
        if job.status not in {"queued", "failed"}:
            raise GenerationJobConflict("Generation job must be queued or failed before run")
        prompt = (job.edited_prompt_text or job.prompt_text or "").strip()
        if not prompt:
            raise GenerationJobConflict("Generation prompt is required")
        repo.mark_running(job_id)
        try:
            if not self.api_key:
                raise XAIAPIAuthError("Add an xAI API key in Config before generating")
            parameters = job.parameters or {}
            input_images = self._input_image_data_urls(job, Path(library_path))
            quality = _normalize_quality(parameters.get("quality"))
            aspect_ratio = _normalize_aspect_ratio(
                parameters.get("requested_aspect_ratio") or parameters.get("aspect_ratio")
            )
            image_bytes, mime_type, zero_data_retention = self._generate(
                prompt,
                input_images=input_images,
                quality=quality,
                aspect_ratio=aspect_ratio,
            )
            suffix = ".png" if mime_type == "image/png" else ".jpg"
            metadata = {
                "provider": PROVIDER_ID,
                "auth_mode": self.auth_mode,
                "model": MODEL,
                "image_model": MODEL,
                "quality": quality,
                "resolution": "1k",
                "requested_aspect_ratio": aspect_ratio,
                "response_format": "b64_json",
                "zero_data_retention": zero_data_retention,
                "mode": "image_edit" if input_images else "text_to_image",
                "input_image_count": len(input_images),
            }
            return repo.stage_result(job_id, image_bytes, f"xai-grok-imagine{suffix}", metadata)
        except GenerationJobConflict as exc:
            repo.mark_failed(job_id, str(exc))
            raise
        except XAIAPIRateLimitError as exc:
            failed = repo.mark_failed(job_id, str(exc), exc.retry_after_seconds)
            repo.record_provider_rate_limit(PROVIDER_ID, exc.retry_after_seconds)
            raise XAIAPIRateLimitError(
                failed.error or "xAI generation is temporarily rate limited",
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        except Exception as exc:
            failed = repo.mark_failed(job_id, str(exc))
            if isinstance(exc, XAIAPIAuthError):
                raise XAIAPIAuthError(failed.error or "xAI API authentication failed") from exc
            if isinstance(exc, XAIAPITemporaryError):
                raise XAIAPITemporaryError(failed.error or "xAI generation is temporarily unavailable") from exc
            raise XAIAPIError(failed.error or "xAI generation failed") from exc

    def _generate(
        self,
        prompt: str,
        *,
        input_images: list[str],
        quality: str,
        aspect_ratio: str,
    ) -> tuple[bytes, str, bool]:
        payload: dict[str, Any] = {
            "model": MODEL,
            "prompt": prompt,
            "quality": quality,
            "resolution": "1k",
            "aspect_ratio": aspect_ratio,
            "response_format": "b64_json",
        }
        endpoint = "images/generations"
        if input_images:
            endpoint = "images/edits"
            image_payloads = [{"type": "image_url", "url": image_url} for image_url in input_images]
            if len(image_payloads) == 1:
                payload["image"] = image_payloads[0]
            else:
                payload["images"] = image_payloads
        close_client = self.http_client is None
        client = self.http_client or httpx.Client(timeout=httpx.Timeout(self.timeout))
        try:
            try:
                response = client.post(
                    f"{self.base_url}/{endpoint}",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
            except httpx.HTTPError as exc:
                raise XAIAPITemporaryError("xAI generation is temporarily unavailable") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code == 429:
            raise XAIAPIRateLimitError(
                "xAI generation is temporarily rate limited",
                retry_after_seconds=parse_retry_after_seconds(response.headers.get("Retry-After")),
            )
        if response.status_code in {401, 403}:
            raise XAIAPIAuthError("xAI rejected the configured API key")
        if response.status_code == 408 or response.status_code >= 500:
            raise XAIAPITemporaryError("xAI generation is temporarily unavailable")
        if response.status_code != 200:
            raise XAIAPIError(f"xAI rejected the generation request with status {response.status_code}")
        return _response_image(response)

    def _input_image_data_urls(self, job, library_path: Path) -> list[str]:
        raw_images = job.parameters.get("input_images") if isinstance(job.parameters, dict) else None
        if not isinstance(raw_images, list):
            return []
        if len(raw_images) > MAX_INPUT_IMAGES:
            raise XAIAPIError(f"xAI image editing supports up to {MAX_INPUT_IMAGES} input images")
        input_images: list[str] = []
        repo = GenerationJobRepository(library_path)
        for raw in raw_images:
            if not isinstance(raw, dict):
                continue
            source = str(raw.get("source") or "uploaded")
            image_id = raw.get("image_id")
            if source == "library" and isinstance(image_id, str) and image_id:
                result_path = raw.get("result_path")
                if isinstance(result_path, str) and result_path:
                    image_path, mime_type = resolve_generation_input_image_path(
                        library_path,
                        result_path,
                        allowed_roots={"generation-references"},
                    )
                else:
                    _, image_path, mime_type = repo.resolve_library_reference(image_id)
                input_images.append(_data_url(image_path.read_bytes(), mime_type))
                continue
            data_url = raw.get("data_url")
            if isinstance(data_url, str) and data_url:
                data, mime_type = _decode_data_url(data_url)
                input_images.append(_data_url(data, mime_type))
                continue
            result_path = raw.get("result_path")
            if isinstance(result_path, str) and result_path:
                image_path, mime_type = resolve_generation_input_image_path(library_path, result_path)
                input_images.append(_data_url(image_path.read_bytes(), mime_type))
        return input_images
