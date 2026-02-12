"""설문 기반 여행지 추천을 처리하는 비동기 워커 서비스."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from dataclasses import dataclass
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy
from app.schemas.enums import Region
from app.schemas.recommend import (
    BudgetLevel,
    CallbackError,
    FoodPersonality,
    MainInterest,
    RecommendCallbackFailure,
    RecommendCallbackSuccess,
    RecommendedDestination,
    RecommendRequest,
    RecommendResultData,
    SurveyPreference,
    TravelRange,
    TravelStyle,
    Weather,
)
from app.services.callback_delivery import post_callback_with_retry

logger = get_logger(__name__)
DEFAULT_SELECTION_SIZE = 5

VARIATION_HINTS = [
    "인기 명소와 접근성을 조금 더 우선하세요.",
    "너무 뻔한 선택은 줄이고 새로움을 조금 더 반영하세요.",
    "휴식과 여유 중심 분위기를 조금 더 반영하세요.",
    "활동적이고 다채로운 경험을 조금 더 반영하세요.",
    "음식과 미식 경험 관점을 조금 더 반영하세요.",
]

WEATHER_MEANINGS: dict[Weather, str] = {
    "OCEAN_BEACH": "쨍한 햇살 아래 끝없이 펼쳐진 에메랄드빛 바다와 부드러운 모래사장",
    "SNOW_HOT_SPRING": "코끝을 스치는 쌀쌀한 공기와 눈 덮인 산등성이가 보이는 따뜻한 노천탕",
    "CLEAN_CITY_BREEZE": "덥지도 춥지도 않은 선선한 바람을 맞으며 걷기 좋은 깨끗한 도시의 거리",
    "INDOOR_LANDMARK": "날씨와 상관없이 화려한 조명과 에너지가 넘치는 실내 랜드마크",
}

TRAVEL_RANGE_MEANINGS: dict[TravelRange, str] = {
    "SHORT_HAUL": "주말을 활용하여 가볍게 다녀올 수 있는 4시간 이내의 단거리",
    "MEDIUM_HAUL": "기분 전환을 확실히 할 수 있는 5~8시간 정도의 중거리",
    "LONG_HAUL": "완전한 이국적 정취를 위해 10시간 이상의 장거리 비행도 마다하지 않음",
}

TRAVEL_STYLE_MEANINGS: dict[TravelStyle, str] = {
    "MODERN_TRENDY": "세련된 디자인의 건축물과 트렌디한 팝업 스토어가 가득한 현대적 감각",
    "HISTORIC_RELAXED": "수백 년의 세월을 간직한 유적지와 시간이 멈춘 듯한 고즈넉한 역사적 분위기",
    "PURE_NATURE": "인공적인 소음 없이 오직 파도 소리와 새소리만 들리는 압도적인 대자연",
}

BUDGET_LEVEL_MEANINGS: dict[BudgetLevel, str] = {
    "COST_EFFECTIVE": "최소한의 비용으로 현지의 본질을 경험하는 합리적인 가성비 여행",
    "BALANCED": "평소에는 아끼더라도 여행지의 특별한 순간에는 기꺼이 지불하는 균형 잡힌 소비",
    "PREMIUM_LUXURY": "비용에 구애받지 않고 오직 최고의 서비스와 품질만을 지향하는 프리미엄 경험",
}

FOOD_PERSONALITY_MEANINGS: dict[FoodPersonality, str] = {
    "LOCAL_HIDDEN_GEM": "현지인들만 아는 골목 안쪽의 투박하지만 진실된 로컬 노포 탐방",
    "FINE_DINING": "전 세계적으로 검증된 미슐랭 가이드 맛집이나 쾌적한 파인 다이닝",
    "INSTAGRAMMABLE": "맛은 기본, 공간의 인테리어와 플레이팅이 완벽한 인스타 감성 카페 투어",
}

MAIN_INTEREST_MEANINGS: dict[MainInterest, str] = {
    "SHOPPING_TOUR": "유명 브랜드와 로컬 편집숍을 넘나드는 감각적인 쇼핑 투어",
    "DYNAMIC_ACTIVITY": "서핑, 스키, 등산 등 온몸으로 자연을 느끼는 역동적인 액티비티",
    "ART_AND_CULTURE": "미술관과 박물관을 조용히 관람하며 예술적 영감을 채우는 시간",
}


@dataclass(slots=True)
class RegionCandidate:
    """추천 후보 지역."""

    region_name: str


def _strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _describe_single(value: str | None, mapping: dict[str, str]) -> str:
    """단일 enum 값을 코드+설명 문자열로 만든다."""
    if not value:
        return "미선택"
    return f"{value} ({mapping.get(value, '설명 없음')})"


def _describe_multi(values: list[str] | None, mapping: dict[str, str]) -> str:
    """복수 enum 값을 코드+설명 문자열로 만든다."""
    if not values:
        return "미선택"
    return ", ".join(f"{value} ({mapping.get(value, '설명 없음')})" for value in values)


def _build_recommend_prompt(
    survey: SurveyPreference,
    candidates: list[RegionCandidate],
    variation_hint: str,
) -> str:
    """후보 목록 내부에서만 5개를 고르도록 LLM 프롬프트를 구성한다."""
    candidate_names = [candidate.region_name for candidate in candidates]

    weather_text = _describe_single(survey.weather, WEATHER_MEANINGS)
    travel_range_text = _describe_single(survey.travel_range, TRAVEL_RANGE_MEANINGS)
    travel_style_text = _describe_single(survey.travel_style, TRAVEL_STYLE_MEANINGS)
    budget_level_text = _describe_single(survey.budget_level, BUDGET_LEVEL_MEANINGS)
    food_personality_text = _describe_multi(survey.food_personality, FOOD_PERSONALITY_MEANINGS)
    main_interests_text = _describe_multi(survey.main_interests, MAIN_INTEREST_MEANINGS)

    return f"""
당신은 여행지 추천 전문가입니다.

아래는 사용자 설문 응답입니다. 각 항목은 "코드 + 실제 의미"를 포함합니다.
- 날씨: {weather_text}
- 여행 거리: {travel_range_text}
- 여행 스타일: {travel_style_text}
- 예산 성향: {budget_level_text}
- 음식 성향: {food_personality_text}
- 주요 활동: {main_interests_text}

후보 여행지 목록 (반드시 이 목록 안에서만 선택):
{", ".join(candidate_names)}

요구사항:
1) 후보 목록에서 중복 없이 정확히 5개를 선택하세요.
2) 이번 실행 변주 힌트: {variation_hint}

반드시 JSON만 출력하세요. JSON 외 텍스트는 절대 출력하지 마세요.
{{
  "recommended_destinations": [
    {{"region_name": "string"}}
  ]
}}
""".strip()


def _build_request_rng() -> random.Random:
    """요청마다 다른 추천을 유도하기 위한 난수 생성기를 만든다."""
    seed_source = f"{time.time_ns()}-{random.getrandbits(64)}"
    seed_hex = hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:16]
    return random.Random(int(seed_hex, 16))


def _pick_variation_hint(rng: random.Random) -> str:
    """추천 변주 힌트를 하나 선택한다."""
    return rng.choice(VARIATION_HINTS)


def _load_candidates(rng: random.Random) -> list[RegionCandidate]:
    """시스템 내 Region ENUM을 추천 후보 목록으로 로드한다."""
    candidates = [RegionCandidate(region_name=region.value) for region in Region]
    rng.shuffle(candidates)
    return candidates


def _get_recommend_llm() -> ChatOpenAI:
    """추천 전용 LLM 인스턴스를 생성한다."""
    settings = get_settings()
    timeout_policy = get_timeout_policy(settings)
    return ChatOpenAI(
        model=settings.LLM_MODEL_NAME,
        temperature=settings.RECOMMEND_LLM_TEMPERATURE,
        api_key=settings.OPENAI_API_KEY,
        request_timeout=timeout_policy.recommend_timeout_seconds,
    )


def _parse_llm_recommendation(raw_content: str) -> dict[str, Any]:
    cleaned = _strip_markdown_fence(raw_content)
    return json.loads(cleaned)


def _normalize_result(
    parsed: dict[str, Any],
    candidates: list[RegionCandidate],
) -> RecommendResultData:
    """LLM 응답을 검증하고 추천 결과를 정확히 5개로 정규화한다."""
    candidate_names = {candidate.region_name for candidate in candidates}
    candidate_order = [candidate.region_name for candidate in candidates]
    used: set[str] = set()
    normalized: list[RecommendedDestination] = []

    raw_items = parsed.get("recommended_destinations", [])
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, str):
                region_name = item
            elif isinstance(item, dict):
                region_name = item.get("region_name")
            else:
                continue

            if not isinstance(region_name, str) or region_name not in candidate_names:
                continue
            if region_name in used:
                continue

            used.add(region_name)
            normalized.append(RecommendedDestination(region_name=region_name))
            if len(normalized) == DEFAULT_SELECTION_SIZE:
                break

    if len(normalized) < DEFAULT_SELECTION_SIZE:
        for region_name in candidate_order:
            if region_name in used:
                continue
            normalized.append(RecommendedDestination(region_name=region_name))
            used.add(region_name)
            if len(normalized) == DEFAULT_SELECTION_SIZE:
                break

    if len(normalized) < DEFAULT_SELECTION_SIZE:
        raise RuntimeError("INSUFFICIENT_DESTINATIONS")

    return RecommendResultData(recommended_destinations=normalized)


async def run_recommendation_pipeline(request: RecommendRequest) -> RecommendResultData:
    """추천 작업에 대해 후보 로드와 LLM 선정을 수행한다."""
    survey = request.to_survey()
    rng = _build_request_rng()
    candidates = _load_candidates(rng)
    variation_hint = _pick_variation_hint(rng)
    prompt = _build_recommend_prompt(survey, candidates, variation_hint)

    response = await asyncio.to_thread(_get_recommend_llm().invoke, prompt)
    raw_content = response.content if isinstance(response.content, str) else str(response.content)
    parsed = _parse_llm_recommendation(raw_content)
    return _normalize_result(parsed, candidates)


def _build_callback_url(base_url: str, job_id: str) -> str:
    """설정된 콜백 베이스 URL로부터 최종 콜백 엔드포인트를 생성한다."""
    callback = base_url.rstrip("/")
    if "{jobId}" in callback:
        return callback.replace("{jobId}", job_id)
    if "{job_id}" in callback:
        return callback.replace("{job_id}", job_id)
    if callback.endswith(f"/surveys/{job_id}/result"):
        return callback
    if callback.endswith("/surveys/callback"):
        return f"{callback[: -len('/callback')]}/{job_id}/result"
    return f"{callback}/surveys/{job_id}/result"


async def _post_callback(
    callback_url: str,
    payload: dict,
    timeout_seconds: int,
    service_secret: str,
    job_id: str,
) -> None:
    headers = {"x-service-secret": service_secret} if service_secret else {}
    await post_callback_with_retry(
        callback_url=callback_url,
        payload=payload,
        headers=headers,
        timeout_seconds=timeout_seconds,
        context={"job_id": job_id, "callback_type": "recommend"},
    )


async def process_recommend_request(request: RecommendRequest) -> None:
    """추천 요청을 처리하고 완료/실패 결과를 NestJS 콜백으로 전달한다."""
    settings = get_settings()
    timeout_policy = get_timeout_policy(settings)
    callback_endpoint = _build_callback_url(str(request.callback_url), request.job_id)

    try:
        result = await asyncio.wait_for(
            run_recommendation_pipeline(request),
            timeout=timeout_policy.recommend_timeout_seconds,
        )
        callback_payload = RecommendCallbackSuccess(status="SUCCESS", data=result).model_dump(mode="json")
    except asyncio.TimeoutError:
        callback_payload = RecommendCallbackFailure(
            status="FAILED",
            error=CallbackError(code="LLM_TIMEOUT", message="Analysis took too long to complete."),
        ).model_dump(mode="json")
    except Exception as exc:
        logger.exception("Recommendation pipeline failed: %s", exc)
        callback_payload = RecommendCallbackFailure(
            status="FAILED",
            error=CallbackError(code="PIPELINE_ERROR", message=str(exc)),
        ).model_dump(mode="json")

    await _post_callback(
        callback_url=callback_endpoint,
        payload=callback_payload,
        timeout_seconds=timeout_policy.callback_timeout_seconds,
        service_secret=settings.SERVICE_SECRET,
        job_id=request.job_id,
    )
