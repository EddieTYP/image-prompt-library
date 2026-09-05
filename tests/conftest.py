import pytest


@pytest.fixture(autouse=True)
def allow_test_client_hostname(monkeypatch):
    monkeypatch.setenv("IMAGE_PROMPT_LIBRARY_ALLOWED_HOSTS", "testserver")
