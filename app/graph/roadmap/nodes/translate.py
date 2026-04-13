"""로드맵 장소명 한국어 정규화 노드."""

from __future__ import annotations

import asyncio
import json
import re

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.job_log_context import append_job_log
from app.core.llm_router import Stage, ainvoke
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy
from app.graph.roadmap.state import RoadmapState
from app.graph.roadmap.utils import strip_code_fence

logger = get_logger(__name__)


class PlaceNameTranslation(BaseModel):
    """단일 장소명 정규화 결과."""

    place_id: str = Field(..., description="Google Places ID")
    display_name: str = Field(..., description="한국어 우선 표기용 장소명")


class PlaceNameTranslationPlan(BaseModel):
    """장소명 정규화 LLM 결과."""

    items: list[PlaceNameTranslation] = Field(default_factory=list, description="정규화된 장소명 목록")


_HANGUL_RE = re.compile(r"[가-힣]")


def _contains_hangul(text: str) -> bool:
    return bool(_HANGUL_RE.search(text))


def _needs_translation(name: str) -> bool:
    normalized = (name or "").strip()
    if not normalized:
        return False
    return not _contains_hangul(normalized)


def _extract_place_records(fetched_places: dict[str, list]) -> list[dict]:
    """정규화가 필요한 장소 후보를 place_id 기준으로 수집합니다."""
    records: list[dict] = []
    seen: set[str] = set()

    for slot_places in fetched_places.values():
        for place in slot_places:
            place_id = str(place.get("place_id") or "").strip()
            name = str(place.get("name") or "").strip()
            if not place_id or not name or place_id in seen:
                continue
            if not _needs_translation(name):
                continue
            seen.add(place_id)
            records.append(
                {
                    "place_id": place_id,
                    "original_name": name,
                    "address": place.get("address"),
                    "types": place.get("types") or [],
                }
            )

    return records


def _apply_display_names(fetched_places: dict[str, list], display_names_by_place_id: dict[str, str]) -> dict[str, list]:
    """모든 fetched_places 항목에 display_name을 채웁니다."""
    normalized: dict[str, list] = {}
    for slot_key, slot_places in fetched_places.items():
        updated_places: list[dict] = []
        for place in slot_places:
            place_id = str(place.get("place_id") or "").strip()
            original_name = str(place.get("name") or "").strip()
            display_name = str(display_names_by_place_id.get(place_id) or "").strip()
            if not display_name:
                display_name = original_name
            updated_places.append(
                {
                    **place,
                    "display_name": display_name or original_name,
                }
            )
        normalized[slot_key] = updated_places
    return normalized


async def _translate_place_names(records: list[dict]) -> dict[str, str]:
    """LLM으로 장소명을 한국어 우선 표기로 정규화합니다."""
    if not records:
        return {}

    parser = PydanticOutputParser(pydantic_object=PlaceNameTranslationPlan)
    timeout_seconds = get_timeout_policy().llm_timeout_seconds

    system_prompt = (
        "당신은 Google Places 장소명을 한국어 사용자용 표기로 정규화하는 전문가입니다.\n"
        "입력된 장소명은 가능한 한 자연스러운 한국어 표기로 바꾸세요.\n"
        "장소명이 이미 한국어이면 그대로 유지하세요.\n"
        "고유명사, 브랜드명, 관광지명은 한국어에서 일반적으로 쓰는 표기를 우선하세요.\n"
        "확신이 없으면 원본명을 유지하세요.\n"
        "절대 새로운 장소를 만들거나 place_id를 바꾸지 마세요.\n"
        "JSON만 반환하세요."
    )
    user_prompt = (
        "아래 장소 목록의 display_name을 한국어 우선 표기로 정규화해주세요.\n"
        "입력 데이터:\n{places}\n\n{format_instructions}"
    )

    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", user_prompt)])
    messages = prompt.format_messages(
        places=json.dumps(records, ensure_ascii=False, indent=2),
        format_instructions=parser.get_format_instructions(),
    )

    try:
        response = await asyncio.wait_for(
            ainvoke(Stage.ROADMAP_PLACE_TRANSLATE, messages, timeout_seconds=timeout_seconds),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("Roadmap place translation timed out: count=%d timeout=%s", len(records), timeout_seconds)
        return {}
    except Exception:
        logger.exception("Roadmap place translation call failed")
        return {}

    try:
        content = strip_code_fence(response.content)
        parsed = parser.parse(content)
    except Exception:
        logger.exception("Roadmap place translation parse failed")
        return {}

    display_names: dict[str, str] = {}
    for item in parsed.items:
        place_id = item.place_id.strip()
        display_name = item.display_name.strip()
        if not place_id or not display_name:
            continue
        display_names[place_id] = display_name

    return display_names


async def normalize_place_names(state: RoadmapState) -> RoadmapState:
    """fetch된 장소명에 한국어 display_name을 채웁니다."""
    if state.get("error"):
        return state

    fetched_places = state.get("fetched_places")
    if not fetched_places:
        return {**state, "error": "normalize_place_names에는 fetched_places가 필요합니다."}

    records = _extract_place_records(fetched_places)
    if not records:
        normalized = _apply_display_names(
            fetched_places,
            {
                str(place.get("place_id") or "").strip(): str(place.get("name") or "").strip()
                for slot_places in fetched_places.values()
                for place in slot_places
                if str(place.get("place_id") or "").strip()
            },
        )
        append_job_log("place_normalize", "candidates=0 normalized=0 fallback=identity")
        return {**state, "fetched_places": normalized}

    display_names = await _translate_place_names(records)
    normalized = _apply_display_names(fetched_places, display_names)

    normalized_count = sum(
        1
        for slot_places in normalized.values()
        for place in slot_places
        if str(place.get("display_name") or "").strip() and place.get("display_name") != place.get("name")
    )
    fallback_count = len(records) - len(display_names)
    append_job_log(
        "place_normalize",
        f"candidates={len(records)} normalized={len(display_names)} fallback={fallback_count}",
    )
    logger.info(
        "Roadmap place normalization completed: candidates=%d normalized=%d fallback=%d changed=%d",
        len(records),
        len(display_names),
        fallback_count,
        normalized_count,
    )
    return {**state, "fetched_places": normalized}
