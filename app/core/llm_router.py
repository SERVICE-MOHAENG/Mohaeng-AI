"""Stage 기반 LLM 라우팅 유틸."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from time import perf_counter
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy

logger = get_logger(__name__)


class Tier(StrEnum):
    """Stage 라우팅 tier."""

    QUALITY = "QUALITY"
    SPEED = "SPEED"
    COST = "COST"


class Stage(StrEnum):
    """LLM 호출 stage."""

    CHAT_INTENT_ROUTING = "CHAT_INTENT_ROUTING"
    CHAT_INTENT_STRUCTURING = "CHAT_INTENT_STRUCTURING"
    CHAT_KEYWORD_ASSIST = "CHAT_KEYWORD_ASSIST"
    CHAT_PLACE_RERANK = "CHAT_PLACE_RERANK"
    CHAT_RESPONSE = "CHAT_RESPONSE"
    CHAT_VISIT_TIME = "CHAT_VISIT_TIME"
    ROADMAP_SKELETON = "ROADMAP_SKELETON"
    ROADMAP_PLACE_RERANK = "ROADMAP_PLACE_RERANK"
    ROADMAP_PLACE_DETAIL = "ROADMAP_PLACE_DETAIL"
    ROADMAP_SUMMARY = "ROADMAP_SUMMARY"
    RECOMMEND_SELECTION = "RECOMMEND_SELECTION"


_STAGE_TIER_MAP: dict[Stage, Tier] = {
    Stage.CHAT_INTENT_ROUTING: Tier.SPEED,
    Stage.CHAT_INTENT_STRUCTURING: Tier.QUALITY,
    Stage.CHAT_KEYWORD_ASSIST: Tier.COST,
    Stage.CHAT_PLACE_RERANK: Tier.COST,
    Stage.CHAT_RESPONSE: Tier.SPEED,
    Stage.CHAT_VISIT_TIME: Tier.SPEED,
    Stage.ROADMAP_SKELETON: Tier.QUALITY,
    Stage.ROADMAP_PLACE_RERANK: Tier.COST,
    Stage.ROADMAP_PLACE_DETAIL: Tier.SPEED,
    Stage.ROADMAP_SUMMARY: Tier.QUALITY,
    Stage.RECOMMEND_SELECTION: Tier.COST,
}


def stage_to_tier(stage: Stage) -> Tier:
    """Stage를 tier로 매핑합니다."""
    return _STAGE_TIER_MAP[stage]


def _normalize_model_name(model_name: str) -> str:
    return model_name.strip()


def _tier_model_name(tier: Tier, settings: Settings) -> str:
    if tier == Tier.QUALITY:
        return _normalize_model_name(settings.LLM_MODEL_QUALITY)
    if tier == Tier.SPEED:
        return _normalize_model_name(settings.LLM_MODEL_SPEED)
    return _normalize_model_name(settings.LLM_MODEL_COST)


def resolve_model(stage: Stage, settings: Settings | None = None) -> tuple[str, Tier | None, bool]:
    """설정과 stage를 기반으로 최종 모델을 선택합니다."""
    resolved_settings = settings or get_settings()
    fallback_model = _normalize_model_name(resolved_settings.LLM_MODEL_NAME)

    if not resolved_settings.ENABLE_STAGE_LLM_ROUTING:
        return fallback_model, None, False

    tier = stage_to_tier(stage)
    tier_model = _tier_model_name(tier, resolved_settings)
    model = tier_model or fallback_model
    return model, tier, True


@lru_cache(maxsize=128)
def _get_chat_openai_client(
    model: str,
    temperature: float,
    timeout_seconds: int,
    api_key: str,
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        request_timeout=timeout_seconds,
    )


def clear_llm_client_cache() -> None:
    """테스트/운영 시 클라이언트 캐시를 비웁니다."""
    _get_chat_openai_client.cache_clear()


def _resolve_timeout_seconds(timeout_seconds: int | None, settings: Settings) -> int:
    if timeout_seconds is None:
        return get_timeout_policy(settings).llm_timeout_seconds
    return max(1, int(timeout_seconds))


def _resolve_temperature(temperature: float | None) -> float:
    if temperature is None:
        return 0.0
    return float(temperature)


def _log_success(
    *,
    stage: Stage,
    tier: Tier | None,
    selected_model: str,
    routing_enabled: bool,
    fallback_used: bool,
    latency_ms: float,
) -> None:
    logger.info(
        "LLM call succeeded",
        extra={
            "stage": stage.value,
            "tier": tier.value if tier else None,
            "selected_model": selected_model,
            "routing_enabled": routing_enabled,
            "fallback_used": fallback_used,
            "latency_ms": latency_ms,
        },
    )


def _log_failure(
    *,
    stage: Stage,
    tier: Tier | None,
    selected_model: str,
    routing_enabled: bool,
    fallback_used: bool,
    latency_ms: float,
    message: str,
    exc: Exception,
) -> None:
    logger.warning(
        message,
        extra={
            "stage": stage.value,
            "tier": tier.value if tier else None,
            "selected_model": selected_model,
            "routing_enabled": routing_enabled,
            "fallback_used": fallback_used,
            "latency_ms": latency_ms,
        },
        exc_info=exc,
    )


def invoke(
    stage: Stage,
    payload: Any,
    *,
    settings: Settings | None = None,
    timeout_seconds: int | None = None,
    temperature: float | None = None,
) -> Any:
    """Stage 기준으로 모델을 선택해 동기 LLM 호출을 수행합니다."""
    resolved_settings = settings or get_settings()
    resolved_timeout = _resolve_timeout_seconds(timeout_seconds, resolved_settings)
    resolved_temperature = _resolve_temperature(temperature)
    selected_model, tier, routing_enabled = resolve_model(stage, resolved_settings)
    fallback_model = _normalize_model_name(resolved_settings.LLM_MODEL_NAME)

    started = perf_counter()
    try:
        client = _get_chat_openai_client(
            selected_model,
            resolved_temperature,
            resolved_timeout,
            resolved_settings.OPENAI_API_KEY,
        )
        response = client.invoke(payload)
        _log_success(
            stage=stage,
            tier=tier,
            selected_model=selected_model,
            routing_enabled=routing_enabled,
            fallback_used=False,
            latency_ms=(perf_counter() - started) * 1000,
        )
        return response
    except Exception as exc:
        if (not routing_enabled) or selected_model == fallback_model:
            _log_failure(
                stage=stage,
                tier=tier,
                selected_model=selected_model,
                routing_enabled=routing_enabled,
                fallback_used=False,
                latency_ms=(perf_counter() - started) * 1000,
                message="LLM call failed",
                exc=exc,
            )
            raise

        _log_failure(
            stage=stage,
            tier=tier,
            selected_model=selected_model,
            routing_enabled=routing_enabled,
            fallback_used=False,
            latency_ms=(perf_counter() - started) * 1000,
            message="LLM call failed. Retrying with fallback model.",
            exc=exc,
        )

    fallback_started = perf_counter()
    fallback_client = _get_chat_openai_client(
        fallback_model,
        resolved_temperature,
        resolved_timeout,
        resolved_settings.OPENAI_API_KEY,
    )
    try:
        response = fallback_client.invoke(payload)
        _log_success(
            stage=stage,
            tier=tier,
            selected_model=fallback_model,
            routing_enabled=routing_enabled,
            fallback_used=True,
            latency_ms=(perf_counter() - fallback_started) * 1000,
        )
        return response
    except Exception as fallback_exc:
        _log_failure(
            stage=stage,
            tier=tier,
            selected_model=fallback_model,
            routing_enabled=routing_enabled,
            fallback_used=True,
            latency_ms=(perf_counter() - fallback_started) * 1000,
            message="LLM fallback call failed",
            exc=fallback_exc,
        )
        raise


async def ainvoke(
    stage: Stage,
    payload: Any,
    *,
    settings: Settings | None = None,
    timeout_seconds: int | None = None,
    temperature: float | None = None,
) -> Any:
    """Stage 기준으로 모델을 선택해 비동기 LLM 호출을 수행합니다."""
    resolved_settings = settings or get_settings()
    resolved_timeout = _resolve_timeout_seconds(timeout_seconds, resolved_settings)
    resolved_temperature = _resolve_temperature(temperature)
    selected_model, tier, routing_enabled = resolve_model(stage, resolved_settings)
    fallback_model = _normalize_model_name(resolved_settings.LLM_MODEL_NAME)

    started = perf_counter()
    try:
        client = _get_chat_openai_client(
            selected_model,
            resolved_temperature,
            resolved_timeout,
            resolved_settings.OPENAI_API_KEY,
        )
        response = await client.ainvoke(payload)
        _log_success(
            stage=stage,
            tier=tier,
            selected_model=selected_model,
            routing_enabled=routing_enabled,
            fallback_used=False,
            latency_ms=(perf_counter() - started) * 1000,
        )
        return response
    except Exception as exc:
        if (not routing_enabled) or selected_model == fallback_model:
            _log_failure(
                stage=stage,
                tier=tier,
                selected_model=selected_model,
                routing_enabled=routing_enabled,
                fallback_used=False,
                latency_ms=(perf_counter() - started) * 1000,
                message="LLM async call failed",
                exc=exc,
            )
            raise

        _log_failure(
            stage=stage,
            tier=tier,
            selected_model=selected_model,
            routing_enabled=routing_enabled,
            fallback_used=False,
            latency_ms=(perf_counter() - started) * 1000,
            message="LLM async call failed. Retrying with fallback model.",
            exc=exc,
        )

    fallback_started = perf_counter()
    fallback_client = _get_chat_openai_client(
        fallback_model,
        resolved_temperature,
        resolved_timeout,
        resolved_settings.OPENAI_API_KEY,
    )
    try:
        response = await fallback_client.ainvoke(payload)
        _log_success(
            stage=stage,
            tier=tier,
            selected_model=fallback_model,
            routing_enabled=routing_enabled,
            fallback_used=True,
            latency_ms=(perf_counter() - fallback_started) * 1000,
        )
        return response
    except Exception as fallback_exc:
        _log_failure(
            stage=stage,
            tier=tier,
            selected_model=fallback_model,
            routing_enabled=routing_enabled,
            fallback_used=True,
            latency_ms=(perf_counter() - fallback_started) * 1000,
            message="LLM async fallback call failed",
            exc=fallback_exc,
        )
        raise
