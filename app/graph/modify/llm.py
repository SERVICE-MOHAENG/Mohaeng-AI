"""로드맵 수정 그래프 LLM 인스턴스 관리."""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


@lru_cache
def get_llm() -> ChatOpenAI:
    """ChatOpenAI 인스턴스를 반환합니다."""
    settings = get_settings()
    return ChatOpenAI(model=settings.LLM_MODEL_NAME, temperature=0, api_key=settings.OPENAI_API_KEY)
