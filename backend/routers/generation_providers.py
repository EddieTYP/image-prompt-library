from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.services.openai_codex_native import (
    CodexDeviceCodeFlow,
    CodexNativeAuthError,
    CodexNativeAuthStore,
    CodexNativeRateLimitError,
    CodexNativeRequestError,
    CodexNativeTemporaryError,
    OpenAICodexNativeProvider,
)

router = APIRouter(prefix="/generation-providers", tags=["generation-providers"])


class CodexNativePollRequest(BaseModel):
    device_auth_id: str
    user_code: str


class CodexNativeTitleSuggestionRequest(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=20_000)


class CodexNativeTitleSuggestionResponse(BaseModel):
    title: str


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
