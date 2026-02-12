"""로드맵 그래프 LLM 인스턴스 관리."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.timeout_policy import get_timeout_policy


@lru_cache
def get_llm() -> ChatOpenAI:
    """ChatOpenAI 인스턴스를 반환합니다."""
    settings = get_settings()
    timeout_policy = get_timeout_policy(settings)
    return ChatOpenAI(
        model=settings.LLM_MODEL_NAME,
        temperature=0,
        api_key=settings.OPENAI_API_KEY,
        request_timeout=timeout_policy.llm_timeout_seconds,
    )
