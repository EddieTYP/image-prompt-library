from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.config import validate_app_owned_paths
from backend.services.openai_codex_native import (
    CodexDeviceCodeFlow,
    CodexNativeAuthError,
    CodexNativeAuthStore,
    CodexNativeRateLimitError,
    CodexNativeRequestError,
    CodexNativeTemporaryError,
    OpenAICodexNativeProvider,
)
from backend.services.xai_api import XAIAPIAuthError, XAIAPIKeyStore, xai_status

router = APIRouter(prefix="/generation-providers", tags=["generation-providers"])


class CodexNativePollRequest(BaseModel):
    device_auth_id: str
    user_code: str


class CodexNativeTitleSuggestionRequest(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=20_000)


class CodexNativeTitleSuggestionResponse(BaseModel):
    title: str


class XAIAPIKeyRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)


@router.get("")
def list_generation_providers(request: Request):
    del request
    return [
        {
            "provider": "manual_upload",
            "display_name": "Manual upload",
            "optional": False,
            "configured": True,
            "authenticated": True,
            "available": True,
            "state": "available",
            "reason": None,
            "status": "ready",
            "message": None,
            "can_generate": True,
            "features": {
                "text_to_image": False,
                "text_reference_to_image": False,
                "image_edit": False,
                "manual_result_upload": True,
            },
        },
        CodexNativeAuthStore().status(),
        xai_status(),
    ]


@router.get("/openai-codex-native/status")
def openai_codex_native_status(request: Request):
    del request
    return CodexNativeAuthStore().status()


@router.post("/openai-codex-native/auth/start")
def openai_codex_native_auth_start(request: Request):
    del request
    try:
        return CodexDeviceCodeFlow().start()
    except CodexNativeAuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/openai-codex-native/auth/poll")
def openai_codex_native_auth_poll(payload: CodexNativePollRequest, request: Request):
    del request
    try:
        return CodexDeviceCodeFlow().poll_device_authorization(payload.device_auth_id, payload.user_code)
    except CodexNativeAuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/openai-codex-native/auth/disconnect")
def openai_codex_native_auth_disconnect(request: Request):
    del request
    store = CodexNativeAuthStore()
    store.delete_tokens()
    return store.status()


@router.post("/xai-api/api-key")
def xai_api_key_save(payload: XAIAPIKeyRequest, request: Request):
    if xai_status().get("managed_by_environment"):
        raise HTTPException(status_code=409, detail="xAI is managed by the XAI_API_KEY environment variable.")
    try:
        validate_app_owned_paths(request.app.state.library_path)
        store = XAIAPIKeyStore()
        store.save_key(payload.api_key)
        return xai_status(store)
    except (ValueError, XAIAPIAuthError, OSError) as exc:
        raise HTTPException(status_code=409, detail="Could not save the xAI API key securely.") from exc


@router.delete("/xai-api/api-key")
def xai_api_key_delete(request: Request):
    if xai_status().get("managed_by_environment"):
        raise HTTPException(status_code=409, detail="xAI is managed by the XAI_API_KEY environment variable.")
    try:
        validate_app_owned_paths(request.app.state.library_path)
        store = XAIAPIKeyStore()
        store.delete_key()
        return xai_status(store)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=409, detail="Could not remove the saved xAI API key.") from exc


@router.post("/openai-codex-native/suggest-title", response_model=CodexNativeTitleSuggestionResponse)
def openai_codex_native_suggest_title(payload: CodexNativeTitleSuggestionRequest, request: Request):
    try:
        title = OpenAICodexNativeProvider(timeout=30.0).suggest_title(
            request.app.state.library_path,
            payload.prompt_text,
        )
        return {"title": title}
    except CodexNativeRateLimitError as exc:
        headers = {"Retry-After": str(exc.retry_after_seconds)} if exc.retry_after_seconds is not None else None
        raise HTTPException(status_code=429, detail="Title suggestion is temporarily rate limited.", headers=headers) from exc
    except CodexNativeTemporaryError as exc:
        raise HTTPException(status_code=503, detail="Title suggestion is temporarily unavailable.") from exc
    except CodexNativeRequestError as exc:
        raise HTTPException(status_code=502, detail="Could not suggest a title.") from exc
    except CodexNativeAuthError as exc:
        raise HTTPException(status_code=409, detail="Connect ChatGPT / Codex OAuth before suggesting a title.") from exc
