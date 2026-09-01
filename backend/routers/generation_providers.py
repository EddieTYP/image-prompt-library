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
from backend.services.xai_grok_oauth import (
    GrokDeviceCodeFlow,
    GrokOAuthAuthStore,
    GrokOAuthError,
    GrokOAuthRateLimitError,
    GrokOAuthRequestError,
    GrokOAuthTemporaryError,
    XaiGrokOAuthProvider,
)

router = APIRouter(prefix="/generation-providers", tags=["generation-providers"])


class CodexNativePollRequest(BaseModel):
    device_auth_id: str
    user_code: str


class GrokOAuthPollRequest(BaseModel):
    device_code: str


class TitleSuggestionRequest(BaseModel):
    prompt_text: str = Field(min_length=1, max_length=20_000)


class LegacyTitleSuggestionResponse(BaseModel):
    title: str


class TitleSuggestionResponse(LegacyTitleSuggestionResponse):
    provider: str


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
                "title_suggestion": False,
            },
        },
        CodexNativeAuthStore().status(),
        GrokOAuthAuthStore().status(),
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


@router.get("/xai-grok-oauth/status")
def xai_grok_oauth_status(request: Request):
    del request
    return GrokOAuthAuthStore().status()


@router.post("/xai-grok-oauth/auth/start")
def xai_grok_oauth_auth_start(request: Request):
    del request
    try:
        return GrokDeviceCodeFlow().start()
    except GrokOAuthTemporaryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GrokOAuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/xai-grok-oauth/auth/poll")
def xai_grok_oauth_auth_poll(payload: GrokOAuthPollRequest, request: Request):
    del request
    try:
        return GrokDeviceCodeFlow().poll_device_authorization(payload.device_code)
    except GrokOAuthTemporaryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GrokOAuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/xai-grok-oauth/auth/disconnect")
def xai_grok_oauth_auth_disconnect(request: Request):
    del request
    store = GrokOAuthAuthStore()
    store.delete_tokens()
    return store.status()


def _suggest_title(provider_id: str, payload: TitleSuggestionRequest, request: Request) -> dict[str, str]:
    if provider_id == "openai_codex_oauth_native":
        provider = OpenAICodexNativeProvider(timeout=30.0)
        login_message = "Connect ChatGPT / Codex OAuth before suggesting a title."
    elif provider_id == "xai_grok_oauth":
        provider = XaiGrokOAuthProvider(timeout=30.0)
        login_message = "Connect Grok OAuth before suggesting a title."
    else:
        raise HTTPException(status_code=404, detail="Title suggestion provider was not found.")
    try:
        title = provider.suggest_title(
            request.app.state.library_path,
            payload.prompt_text,
        )
        return {"title": title, "provider": provider_id}
    except (CodexNativeRateLimitError, GrokOAuthRateLimitError) as exc:
        headers = {"Retry-After": str(exc.retry_after_seconds)} if exc.retry_after_seconds is not None else None
        raise HTTPException(status_code=429, detail="Title suggestion is temporarily rate limited.", headers=headers) from exc
    except (CodexNativeTemporaryError, GrokOAuthTemporaryError) as exc:
        raise HTTPException(status_code=503, detail="Title suggestion is temporarily unavailable.") from exc
    except (CodexNativeRequestError, GrokOAuthRequestError) as exc:
        raise HTTPException(status_code=502, detail="Could not suggest a title.") from exc
    except (CodexNativeAuthError, GrokOAuthError) as exc:
        raise HTTPException(status_code=409, detail=login_message) from exc


@router.post("/openai-codex-native/suggest-title", response_model=LegacyTitleSuggestionResponse)
def openai_codex_native_suggest_title(payload: TitleSuggestionRequest, request: Request):
    return _suggest_title("openai_codex_oauth_native", payload, request)


@router.post("/{provider_id}/suggest-title", response_model=TitleSuggestionResponse)
def provider_suggest_title(provider_id: str, payload: TitleSuggestionRequest, request: Request):
    return _suggest_title(provider_id, payload, request)
