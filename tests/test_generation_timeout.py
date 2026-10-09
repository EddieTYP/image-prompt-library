from types import SimpleNamespace

import httpx
import pytest

from backend.schemas import GenerationJobCreate
from backend.services.generation_jobs import GenerationJobRepository
from backend.services import openai_codex_native as native
from backend.services import xai_grok_oauth as grok


@pytest.mark.parametrize("provider_id", [native.PROVIDER_ID, grok.PROVIDER_ID])
@pytest.mark.parametrize("message", ["", "The read operation timed out"])
@pytest.mark.parametrize("status_code", [None, 408, 504])
def test_provider_timeout_is_persisted_as_uncertain_without_retry(tmp_path, monkeypatch, provider_id, message, status_code):
    library = tmp_path / "library"
    for name in ("AUTH", "GROK_AUTH", "CONFIG"):
        monkeypatch.setenv(f"IMAGE_PROMPT_LIBRARY_{name}_PATH", str(tmp_path / f"{name}.json"))
    repo = GenerationJobRepository(library)
    job = repo.create_job(GenerationJobCreate(provider=provider_id, prompt_text="Timeout fixture"))
    calls = []

    def timeout(request):
        calls.append(request)
        if status_code is not None:
            return httpx.Response(status_code, json={"error": {"message": message or "test-only-token"}}, request=request)
        raise httpx.ReadTimeout(message, request=request)

    auth = SimpleNamespace(read_tokens=lambda **kwargs: {"access_token": "test-only-token"})
    client = httpx.Client(transport=httpx.MockTransport(timeout))
    if provider_id == native.PROVIDER_ID:
        monkeypatch.setattr(native.httpx, "Client", lambda **kwargs: client)
        provider = native.OpenAICodexNativeProvider(auth_store=auth)
        error_type = native.CodexNativeAuthError
    else:
        provider = grok.XaiGrokOAuthProvider(auth_store=auth, http_client=client)
        error_type = grok.GrokOAuthError
    try:
        with pytest.raises(error_type, match="billing status are unknown"):
            provider.run_job(library, job.id)
    finally:
        client.close()
    failed = GenerationJobRepository(library).get_job(job.id)
    assert failed.status == "failed"
    assert failed.metadata["error_kind"] == "provider_timeout"
    assert len(calls) == 1
    assert "test-only-token" not in failed.error
