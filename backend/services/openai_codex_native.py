from __future__ import annotations

import base64
import binascii
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from backend.services.generation_jobs import GenerationJobConflict, GenerationJobRepository

PROVIDER_ID = "openai_codex_oauth_native"
AUTH_MODE = "codex_oauth_native"
DEFAULT_AUTH_PATH = Path.home() / ".image-prompt-library" / "auth.json"
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_AUTH_ISSUER = "https://auth.openai.com"
CODEX_TOKEN_URL = f"{CODEX_AUTH_ISSUER}/oauth/token"
CODEX_CHAT_MODEL = "gpt-5.1-codex-mini"
IMAGE_MODEL = "gpt-image-2"
DEFAULT_QUALITY = "high"

SIZES = {
    "square": "1024x1024",
    "1:1": "1024x1024",
    "landscape": "1536x1024",
    "16:9": "1536x1024",
    "portrait": "1024x1536",
    "9:16": "1024x1536",
}


class CodexNativeAuthError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _auth_path() -> Path:
    configured = os.environ.get("IMAGE_PROMPT_LIBRARY_AUTH_PATH")
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_AUTH_PATH


def _codex_client_id() -> str:
    client_id = os.environ.get("IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID", "").strip()
    if client_id:
        return client_id
    raise CodexNativeAuthError(
        "IMAGE_PROMPT_LIBRARY_CODEX_CLIENT_ID is required to start native Codex OAuth"
    )


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(payload_b64.encode())
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def account_id_from_access_token(token: str) -> str | None:
    claims = _decode_jwt_payload(token)
    auth_claim = claims.get("https://api.openai.com/auth")
    if isinstance(auth_claim, dict):
        account_id = auth_claim.get("chatgpt_account_id")
        if isinstance(account_id, str) and account_id.strip():
            return account_id.strip()
    return None


def codex_cloudflare_headers(access_token: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "codex_cli_rs/0.0.0 (Image Prompt Library)",
        "originator": "codex_cli_rs",
        "Accept": "application/json",
    }
    account_id = account_id_from_access_token(access_token)
    if account_id:
        headers["ChatGPT-Account-ID"] = account_id
    return headers


def _response_json(response: httpx.Response, context: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise CodexNativeAuthError(f"{context} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise CodexNativeAuthError(f"{context} returned an invalid response shape")
    return payload


def _response_int(payload: dict[str, Any], key: str, default: int, context: str) -> int:
    try:
        return int(payload.get(key, default) or default)
    except (TypeError, ValueError) as exc:
        raise CodexNativeAuthError(f"{context} returned invalid {key}") from exc


class CodexNativeAuthStore:

    """App-owned Codex OAuth token store.

    Tokens are intentionally kept outside the image library folder by default
    and status output is redacted so API responses never include secrets.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path).expanduser() if path is not None else _auth_path()

    def save_tokens(self, tokens: dict[str, str]) -> None:
        access_token = str(tokens.get("access_token", "") or "").strip()
        refresh_token = str(tokens.get("refresh_token", "") or "").strip()
        if not access_token or not refresh_token:
            raise CodexNativeAuthError("Codex native auth requires access_token and refresh_token")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        payload = {
            "provider": PROVIDER_ID,
            "auth_mode": AUTH_MODE,
            "tokens": {"access_token": access_token, "refresh_token": refresh_token},
            "base_url": CODEX_BASE_URL,
            "last_refresh": _utc_now(),
        }
        serialized = json.dumps(payload, indent=2)
        fd, temp_name = tempfile.mkstemp(prefix="auth-", suffix=".tmp", dir=self.path.parent)
        temp_path = Path(temp_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
            os.replace(temp_path, self.path)
            self.path.chmod(0o600)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            finally:
                raise

    def read_tokens(self) -> dict[str, str]:
        if not self.path.is_file():
            raise CodexNativeAuthError("No native Codex OAuth credentials saved")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        tokens = payload.get("tokens") if isinstance(payload, dict) else None
        if not isinstance(tokens, dict):
            raise CodexNativeAuthError("Native Codex auth store is missing tokens")
        access_token = str(tokens.get("access_token", "") or "").strip()
        refresh_token = str(tokens.get("refresh_token", "") or "").strip()
        if not access_token or not refresh_token:
            raise CodexNativeAuthError("Native Codex auth store has incomplete tokens")
        return {"access_token": access_token, "refresh_token": refresh_token}

    def status(self) -> dict[str, Any]:
        token_present = False
        account_id = None
        try:
            tokens = self.read_tokens()
            token_present = True
            account_id = account_id_from_access_token(tokens["access_token"])
        except Exception:
            token_present = False
        return {
            "provider": PROVIDER_ID,
            "auth_mode": AUTH_MODE,
            "available": token_present,
            "token_present": token_present,
            "account_id": account_id,
            "auth_store_path": str(self.path),
        }


class CodexDeviceCodeFlow:
    def __init__(self, auth_store: CodexNativeAuthStore | None = None, http_client: httpx.Client | None = None):
        self.auth_store = auth_store or CodexNativeAuthStore()
        self.http_client = http_client

    def _client(self) -> httpx.Client:
        return self.http_client or httpx.Client(timeout=httpx.Timeout(15.0))

    def start(self) -> dict[str, Any]:
        client_id = _codex_client_id()
        close_client = self.http_client is None
        client = self._client()
        try:
            try:
                response = client.post(
                    f"{CODEX_AUTH_ISSUER}/api/accounts/deviceauth/usercode",
                    json={"client_id": client_id},
                    headers={"Content-Type": "application/json"},
                )
            except httpx.HTTPError as exc:
                raise CodexNativeAuthError("Device code request failed") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code != 200:
            raise CodexNativeAuthError(f"Device code request returned status {response.status_code}")
        payload = _response_json(response, "Device code request")
        user_code = str(payload.get("user_code", "") or "").strip()
        device_auth_id = str(payload.get("device_auth_id", "") or "").strip()
        interval = max(3, _response_int(payload, "interval", 5, "Device code request"))
        if not user_code or not device_auth_id:
            raise CodexNativeAuthError("Device code response missing user_code or device_auth_id")
        return {
            "provider": PROVIDER_ID,
            "auth_mode": AUTH_MODE,
            "user_code": user_code,
            "device_auth_id": device_auth_id,
            "verification_url": f"{CODEX_AUTH_ISSUER}/codex/device",
            "interval": interval,
            "expires_in": 15 * 60,
        }

    def poll_device_authorization(self, device_auth_id: str, user_code: str) -> dict[str, Any]:
        device_auth_id = str(device_auth_id or "").strip()
        user_code = str(user_code or "").strip()
        if not device_auth_id or not user_code:
            raise CodexNativeAuthError("device_auth_id and user_code are required")
        close_client = self.http_client is None
        client = self._client()
        try:
            try:
                response = client.post(
                    f"{CODEX_AUTH_ISSUER}/api/accounts/deviceauth/token",
                    json={"device_auth_id": device_auth_id, "user_code": user_code},
                    headers={"Content-Type": "application/json"},
                )
            except httpx.HTTPError as exc:
                raise CodexNativeAuthError("Device auth polling failed") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code in {403, 404}:
            return {"provider": PROVIDER_ID, "auth_mode": AUTH_MODE, "status": "pending"}
        if response.status_code != 200:
            raise CodexNativeAuthError(f"Device auth polling returned status {response.status_code}")
        payload = _response_json(response, "Device auth polling")
        authorization_code = str(payload.get("authorization_code", "") or "").strip()
        code_verifier = str(payload.get("code_verifier", "") or "").strip()
        status = self.exchange_authorization_code(authorization_code, code_verifier)
        status["status"] = "approved"
        return status

    def exchange_authorization_code(self, authorization_code: str, code_verifier: str) -> dict[str, Any]:
        client_id = _codex_client_id()
        code = str(authorization_code or "").strip()
        verifier = str(code_verifier or "").strip()
        if not code or not verifier:
            raise CodexNativeAuthError("authorization_code and code_verifier are required")
        close_client = self.http_client is None
        client = self._client()
        try:
            try:
                response = client.post(
                    CODEX_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": f"{CODEX_AUTH_ISSUER}/deviceauth/callback",
                        "client_id": client_id,
                        "code_verifier": verifier,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            except httpx.HTTPError as exc:
                raise CodexNativeAuthError("Token exchange failed") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code != 200:
            raise CodexNativeAuthError(f"Token exchange returned status {response.status_code}")
        payload = _response_json(response, "Token exchange")
        access_token = str(payload.get("access_token", "") or "").strip()
        refresh_token = str(payload.get("refresh_token", "") or "").strip()
        self.auth_store.save_tokens({"access_token": access_token, "refresh_token": refresh_token})
        return self.auth_store.status()


class OpenAICodexNativeProvider:
    def __init__(self, auth_store: CodexNativeAuthStore | None = None, timeout: float = 120.0):
        self.auth_store = auth_store or CodexNativeAuthStore()
        self.timeout = timeout

    def run_job(self, library_path: Path | str, job_id: str):
        repo = GenerationJobRepository(library_path)
        job = repo.get_job(job_id)
        if job.provider != PROVIDER_ID:
            raise GenerationJobConflict(f"Generation job provider must be {PROVIDER_ID}")
        if job.status not in {"queued", "failed"}:
            raise GenerationJobConflict("Generation job must be queued or failed before run")
        prompt = (job.edited_prompt_text or job.prompt_text or "").strip()
        if not prompt:
            raise GenerationJobConflict("Generation prompt is required")
        repo.mark_running(job_id)
        try:
            parameters = job.parameters or {}
            aspect_ratio = str(parameters.get("aspect_ratio") or "square")
            size = SIZES.get(aspect_ratio, SIZES["square"])
            quality = str(parameters.get("quality") or DEFAULT_QUALITY)
            model = job.model or IMAGE_MODEL
            image_b64 = self._collect_image_b64(prompt, size=size, quality=quality)
            try:
                image_bytes = base64.b64decode(image_b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise CodexNativeAuthError("Codex response contained invalid image data") from exc
            metadata = {
                "provider": PROVIDER_ID,
                "auth_mode": AUTH_MODE,
                "model": model,
                "size": size,
                "quality": quality,
                "source_job_id": job_id,
            }
            return repo.stage_result(job_id, image_bytes, "openai-codex-native.png", metadata)
        except GenerationJobConflict:
            raise
        except Exception as exc:
            repo.mark_failed(job_id, str(exc))
            if isinstance(exc, CodexNativeAuthError):
                raise
            raise CodexNativeAuthError("Codex native generation failed") from exc

    def _collect_image_b64(self, prompt: str, *, size: str, quality: str) -> str:
        tokens = self.auth_store.read_tokens()
        access_token = tokens["access_token"]
        payload = {
            "model": CODEX_CHAT_MODEL,
            "store": False,
            "instructions": "Create exactly one image using the image_generation tool when provided.",
            "input": [{
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }],
            "tools": [{
                "type": "image_generation",
                "model": IMAGE_MODEL,
                "size": size,
                "quality": quality,
                "output_format": "png",
                "background": "opaque",
                "partial_images": 1,
            }],
            "tool_choice": {
                "type": "allowed_tools",
                "mode": "required",
                "tools": [{"type": "image_generation"}],
            },
            "stream": True,
        }
        image_b64: str | None = None
        url = f"{CODEX_BASE_URL}/responses"
        with httpx.Client(timeout=httpx.Timeout(self.timeout)) as client:
            with client.stream("POST", url, headers=codex_cloudflare_headers(access_token), json=payload) as response:
                if response.status_code != 200:
                    raise CodexNativeAuthError(f"Codex Responses API returned status {response.status_code}")
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    if raw == "[DONE]":
                        break
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    event_type = event.get("type")
                    if event_type == "response.image_generation_call.partial_image":
                        partial = event.get("partial_image_b64")
                        if isinstance(partial, str) and partial:
                            image_b64 = partial
                    elif event_type == "response.output_item.done":
                        item = event.get("item")
                        if isinstance(item, dict) and item.get("type") == "image_generation_call":
                            result = item.get("result")
                            if isinstance(result, str) and result:
                                image_b64 = result
        if not image_b64:
            raise CodexNativeAuthError("Codex response contained no image_generation result")
        return image_b64
