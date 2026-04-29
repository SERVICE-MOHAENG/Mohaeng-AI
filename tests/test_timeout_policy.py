"""타임아웃 정책 유틸 테스트."""

from app.core.config import Settings
from app.core.timeout_policy import build_timeout_policy, to_httpx_timeout, to_requests_timeout


def test_build_timeout_policy_uses_long_roadmap_generation_defaults() -> None:
    settings = Settings(
        OPENAI_API_KEY="test-key",
        SERVICE_SECRET="test-service-secret",
        HMAC_SECRET="test-hmac-secret",
    )

    policy = build_timeout_policy(settings)

    assert policy.request_timeout_seconds == 180
    assert policy.llm_timeout_seconds == 180


def test_build_timeout_policy_caps_by_request_timeout() -> None:
    settings = Settings(
        OPENAI_API_KEY="test-key",
        SERVICE_SECRET="test-service-secret",
        HMAC_SECRET="test-hmac-secret",
        REQUEST_TIMEOUT_SECONDS=20,
        LLM_TIMEOUT_SECONDS=60,
        RECOMMEND_TIMEOUT_SECONDS=45,
        EXTERNAL_API_TIMEOUT_SECONDS=50,
        CALLBACK_TIMEOUT_SECONDS=30,
        GOOGLE_PLACES_TIMEOUT_SECONDS=25,
    )

    policy = build_timeout_policy(settings)

    assert policy.request_timeout_seconds == 20
    assert policy.llm_timeout_seconds == 20
    assert policy.recommend_timeout_seconds == 20
    assert policy.external_api_timeout_seconds == 20
    assert policy.callback_timeout_seconds == 20
    assert policy.google_places_timeout_seconds == 20


def test_to_requests_timeout_returns_connect_and_read_timeout() -> None:
    connect_timeout, read_timeout = to_requests_timeout(10)

    assert connect_timeout == 3.0
    assert read_timeout == 7.0


def test_to_httpx_timeout_returns_timeout_object() -> None:
    timeout = to_httpx_timeout(10)

    assert timeout.connect == 3.0
    assert timeout.read == 7.0
