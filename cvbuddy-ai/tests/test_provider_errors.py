import httpx
import pytest

from app.core.config import settings
from app.services.errors import LLMQuotaError, LLMUpstreamError
from app.services.groq import GroqService


class FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict | None = None):
        self.status_code = status_code
        self.payload = payload
        self.headers = headers or {}
        self.text = "private-provider-response-marker"

    def json(self):
        return self.payload


class FakeAsyncClient:
    response: FakeResponse | None = None
    error: Exception | None = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return self.response


@pytest.fixture(autouse=True)
def configure_fake_provider(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "groq_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "mock_llm", False)


@pytest.mark.asyncio
async def test_provider_timeout_has_safe_stable_code(monkeypatch, caplog):
    FakeAsyncClient.error = httpx.ReadTimeout("private-provider-response-marker")
    monkeypatch.setattr("app.services.groq.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(LLMUpstreamError) as raised:
        await GroqService().generate_json(system_instruction="synthetic", user_message="synthetic")

    assert raised.value.code == "provider_timeout"
    assert "private-provider-response-marker" not in str(raised.value)
    assert "private-provider-response-marker" not in caplog.text


@pytest.mark.asyncio
async def test_malformed_provider_response_is_not_logged(monkeypatch, caplog):
    FakeAsyncClient.error = None
    FakeAsyncClient.response = FakeResponse(
        200,
        {"choices": [{"message": {"content": "private-provider-response-marker"}}]},
    )
    monkeypatch.setattr("app.services.groq.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(LLMUpstreamError) as raised:
        await GroqService().generate_json(system_instruction="synthetic", user_message="synthetic")

    assert raised.value.code == "malformed_provider_response"
    assert "private-provider-response-marker" not in str(raised.value)
    assert "private-provider-response-marker" not in caplog.text


@pytest.mark.asyncio
async def test_rate_limit_body_is_not_retained_or_logged(monkeypatch, caplog):
    FakeAsyncClient.error = None
    FakeAsyncClient.response = FakeResponse(429, {}, {"retry-after": "7"})
    monkeypatch.setattr("app.services.groq.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(LLMQuotaError) as raised:
        await GroqService().generate_json(system_instruction="synthetic", user_message="synthetic")

    assert raised.value.retry_after_seconds == 7
    assert "private-provider-response-marker" not in str(raised.value)
    assert "private-provider-response-marker" not in caplog.text


@pytest.mark.asyncio
async def test_provider_gateway_timeout_has_timeout_code(monkeypatch):
    FakeAsyncClient.error = None
    FakeAsyncClient.response = FakeResponse(504, {})
    monkeypatch.setattr("app.services.groq.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(LLMUpstreamError) as raised:
        await GroqService().generate_json(system_instruction="synthetic", user_message="synthetic")

    assert raised.value.code == "provider_timeout"
