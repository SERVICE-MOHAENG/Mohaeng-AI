"""LLM-based place candidate reranking helpers."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.core.llm_router import Stage, ainvoke
from app.core.logger import get_logger
from app.core.timeout_policy import get_timeout_policy
from app.graph.roadmap.utils import strip_code_fence

logger = get_logger(__name__)


class RoadmapRerankChoice(BaseModel):
    """Selected place id per slot."""

    slot_key: str = Field(..., description="Slot identifier")
    place_id: str = Field(..., description="Selected Google place id")


class RoadmapRerankOutput(BaseModel):
    """Rerank output for roadmap day candidates."""

    choices: list[RoadmapRerankChoice] = Field(default_factory=list)


class ChatRerankOutput(BaseModel):
    """Rerank output for chat place replacement."""

    selected_place_id: str = Field(..., description="Selected Google place id")


def _trim_roadmap_slots(slots: list[dict[str, Any]], max_candidates: int) -> list[dict[str, Any]]:
    trimmed: list[dict[str, Any]] = []
    for slot in slots:
        candidates = slot.get("candidates", [])
        trimmed.append(
            {
                "slot_key": slot.get("slot_key"),
                "section": slot.get("section"),
                "area": slot.get("area"),
                "keyword": slot.get("keyword"),
                "candidates": candidates[:max_candidates],
            }
        )
    return trimmed


def _trim_chat_candidates(candidates: list[dict[str, Any]], max_candidates: int) -> list[dict[str, Any]]:
    return candidates[:max_candidates]


async def select_place_ids_for_day(
    *,
    day_number: int,
    slots: list[dict[str, Any]],
    max_candidates: int,
    timeout_seconds: int | None = None,
) -> dict[str, str] | None:
    """Return slot_key -> selected place_id map or None on rerank failure."""
    if not slots:
        return {}

    parser = PydanticOutputParser(pydantic_object=RoadmapRerankOutput)
    timeout = timeout_seconds or get_timeout_policy().llm_timeout_seconds
    trimmed_slots = _trim_roadmap_slots(slots, max_candidates=max_candidates)

    system_prompt = (
        "You are reranking Google Places candidates for itinerary slots.\n"
        "Pick one best place per slot based on slot keyword/area and candidate metadata.\n"
        "Never invent ids. Use only place_id from each slot candidate list.\n"
        "Return JSON only."
    )
    user_prompt = "Day number: {day_number}\nSlot candidates:\n{slots}\n\n{format_instructions}"
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", user_prompt)])
    messages = prompt.format_messages(
        day_number=day_number,
        slots=json.dumps(trimmed_slots, ensure_ascii=False, indent=2),
        format_instructions=parser.get_format_instructions(),
    )

    try:
        response = await asyncio.wait_for(
            ainvoke(Stage.ROADMAP_PLACE_RERANK, messages, timeout_seconds=timeout),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Roadmap place rerank timed out: day=%s timeout=%s", day_number, timeout)
        return None
    except Exception:
        logger.exception("Roadmap place rerank call failed: day=%s", day_number)
        return None

    try:
        raw_content = response.content if isinstance(response.content, str) else str(response.content)
        parsed = parser.parse(strip_code_fence(raw_content))
    except Exception:
        logger.exception("Roadmap place rerank parse failed: day=%s", day_number)
        return None

    candidate_ids_by_slot: dict[str, set[str]] = {}
    for slot in trimmed_slots:
        slot_key = str(slot.get("slot_key") or "").strip()
        if not slot_key:
            continue
        ids = {
            str(candidate.get("place_id") or "").strip()
            for candidate in slot.get("candidates", [])
            if str(candidate.get("place_id") or "").strip()
        }
        if ids:
            candidate_ids_by_slot[slot_key] = ids

    selected: dict[str, str] = {}
    for choice in parsed.choices:
        slot_key = choice.slot_key.strip()
        place_id = choice.place_id.strip()
        if not slot_key or not place_id:
            continue
        if place_id not in candidate_ids_by_slot.get(slot_key, set()):
            continue
        selected[slot_key] = place_id

    return selected or None


async def select_place_id_for_chat(
    *,
    keyword: str,
    candidates: list[dict[str, Any]],
    day: dict[str, Any] | None = None,
    max_candidates: int,
    timeout_seconds: int | None = None,
) -> str | None:
    """Return selected place_id for chat mutation or None on rerank failure."""
    if not candidates:
        return None
    if len(candidates) == 1:
        return str(candidates[0].get("place_id") or "") or None

    parser = PydanticOutputParser(pydantic_object=ChatRerankOutput)
    timeout = timeout_seconds or get_timeout_policy().llm_timeout_seconds
    trimmed_candidates = _trim_chat_candidates(candidates, max_candidates=max_candidates)
    reference_places = [
        {
            "place_name": place.get("place_name"),
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
        }
        for place in (day or {}).get("places", [])[:5]
    ]

    system_prompt = (
        "You are selecting one Google Place candidate for itinerary edit.\n"
        "Pick exactly one place_id from the given candidates that best matches the keyword and day context.\n"
        "Never invent ids. Return JSON only."
    )
    user_prompt = (
        "Search keyword: {keyword}\n"
        "Current day context:\n"
        "{day_context}\n\n"
        "Candidates:\n"
        "{candidates}\n\n"
        "{format_instructions}"
    )
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", user_prompt)])
    messages = prompt.format_messages(
        keyword=keyword,
        day_context=json.dumps(reference_places, ensure_ascii=False, indent=2),
        candidates=json.dumps(trimmed_candidates, ensure_ascii=False, indent=2),
        format_instructions=parser.get_format_instructions(),
    )

    try:
        response = await asyncio.wait_for(
            ainvoke(Stage.CHAT_PLACE_RERANK, messages, timeout_seconds=timeout),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Chat place rerank timed out: timeout=%s", timeout)
        return None
    except Exception:
        logger.exception("Chat place rerank call failed")
        return None

    try:
        raw_content = response.content if isinstance(response.content, str) else str(response.content)
        parsed = parser.parse(strip_code_fence(raw_content))
    except Exception:
        logger.exception("Chat place rerank parse failed")
        return None

    selected_place_id = parsed.selected_place_id.strip()
    candidate_ids = {str(item.get("place_id") or "").strip() for item in trimmed_candidates}
    if selected_place_id not in candidate_ids:
        return None
    return selected_place_id
