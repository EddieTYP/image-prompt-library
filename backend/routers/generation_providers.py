from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.services.openai_codex_native import CodexDeviceCodeFlow, CodexNativeAuthError, CodexNativeAuthStore

router = APIRouter(prefix="/generation-providers", tags=["generation-providers"])


class CodexNativePollRequest(BaseModel):
    device_auth_id: str
    user_code: str


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
