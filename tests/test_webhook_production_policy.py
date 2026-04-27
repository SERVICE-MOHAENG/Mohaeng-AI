"""운영 웹훅 최소 집합 회귀 테스트."""

from pathlib import Path

REMOVED_EVENT_TYPES = (
    "llm_call_success",
    "llm_call_retry",
    "llm_fallback_success",
    "chat_job_completed",
    "generate_job_completed",
    "roadmap_skeleton_completed",
    "roadmap_places_completed",
    "roadmap_finalize_desc",
    "roadmap_finalize_time",
    "roadmap_finalize_completed",
    "chat_mutate_completed",
    "chat_response_completed",
    "chat_intent_routed",
    "chat_intent_parsed",
    "chat_intent_clarification",
)


def test_removed_webhook_event_types_are_not_used_in_app_code() -> None:
    app_root = Path("app")
    python_files = [path for path in app_root.rglob("*.py") if "__pycache__" not in path.parts]
    app_code = "\n".join(path.read_text(encoding="utf-8") for path in python_files)

    for event_type in REMOVED_EVENT_TYPES:
        assert event_type not in app_code
