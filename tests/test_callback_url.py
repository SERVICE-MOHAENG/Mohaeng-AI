"""콜백 URL 생성 공통 유틸 테스트."""

from __future__ import annotations

from app.services.callback_url import build_callback_url


def test_placeholder_job_id_replaced() -> None:
    """URL에 {job_id}가 있으면 job_id로 치환 후 반환한다."""
    url = build_callback_url(
        "https://api.example.com/itineraries/{job_id}/result",
        "job-abc",
        "itineraries/{job_id}/result",
    )
    assert url == "https://api.example.com/itineraries/job-abc/result"


def test_placeholder_job_id_camel_case_replaced() -> None:
    """URL에 {jobId}가 있으면 job_id로 치환 후 반환한다."""
    url = build_callback_url(
        "https://api.example.com/surveys/{jobId}/result",
        "rec-123",
        "surveys/{job_id}/result",
    )
    assert url == "https://api.example.com/surveys/rec-123/result"


def test_already_ends_with_full_path_unchanged() -> None:
    """URL이 이미 default_path(job_id 치환)로 끝나면 그대로 반환한다."""
    base = "https://api.example.com/surveys/job-xyz/result"
    url = build_callback_url(base, "job-xyz", "surveys/{job_id}/result")
    assert url == base


def test_alias_ending_replaced() -> None:
    """alias_endings에 정의된 suffix로 끝나면 해당 path로 치환한다."""
    url = build_callback_url(
        "https://api.example.com/surveys/callback",
        "job-1",
        "surveys/{job_id}/result",
        alias_endings=[("/surveys/callback", "/surveys/{job_id}/result")],
    )
    assert url == "https://api.example.com/surveys/job-1/result"


def test_default_append_when_base_only() -> None:
    """베이스 URL만 주어지면 /{default_path}(job_id 치환)를 붙여 반환한다."""
    url = build_callback_url(
        "https://api.example.com",
        "gen-99",
        "itineraries/{job_id}/result",
    )
    assert url == "https://api.example.com/itineraries/gen-99/result"


def test_base_trailing_slash_stripped() -> None:
    """base_url 끝 '/'는 제거 후 path를 붙인다."""
    url = build_callback_url(
        "https://api.example.com/",
        "job-1",
        "itineraries/{job_id}/result",
    )
    assert url == "https://api.example.com/itineraries/job-1/result"


def test_generate_scenario() -> None:
    """로드맵 생성: default_path만 사용, 베이스만 주어진 경우."""
    url = build_callback_url(
        "https://nestjs.example.com/webhook",
        "generate-job-12345",
        "itineraries/{job_id}/result",
    )
    assert url == "https://nestjs.example.com/webhook/itineraries/generate-job-12345/result"


def test_chat_scenario() -> None:
    """로드맵 대화: default_path만 사용, chat-result path."""
    url = build_callback_url(
        "https://nestjs.example.com/callback",
        "modify-job-456",
        "itineraries/{job_id}/chat-result",
    )
    assert url == "https://nestjs.example.com/callback/itineraries/modify-job-456/chat-result"


def test_recommend_scenario_base_only() -> None:
    """여행지 추천: 베이스만 주어지면 /preferences/jobs/{job_id}/result 붙음."""
    url = build_callback_url(
        "https://api.example.com",
        "recommend-job-789",
        "preferences/jobs/{job_id}/result",
    )
    assert url == "https://api.example.com/preferences/jobs/recommend-job-789/result"


def test_recommend_scenario_placeholder_in_url() -> None:
    """여행지 추천: URL에 {jobId}가 있으면 치환만 하고 path 붙이지 않음."""
    url = build_callback_url(
        "https://api.example.com/preferences/jobs/{jobId}/result",
        "rec-xyz",
        "preferences/jobs/{job_id}/result",
    )
    assert url == "https://api.example.com/preferences/jobs/rec-xyz/result"


def test_recommend_scenario_fully_resolved_nestjs_url() -> None:
    """여행지 추천: NestJS가 완성된 URL을 전달하면 그대로 반환한다 (규칙 2).

    NestJS PreferenceProcessor가 jobId를 resolve한 상태로 callback_url 전달.
    default_path와 path가 일치하므로 rule 2에서 처리됨.
    """
    job_id = "af7aa772-5c04-4435-8f91-9ecbf124bf32"
    base = f"https://api.mohaeng.kr/api/v1/preferences/jobs/{job_id}/result"
    url = build_callback_url(
        base,
        job_id,
        "preferences/jobs/{job_id}/result",
    )
    assert url == base
