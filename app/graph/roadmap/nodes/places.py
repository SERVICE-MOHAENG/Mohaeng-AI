"""로드맵 장소 검색 노드."""

from __future__ import annotations

import asyncio

from langchain_core.runnables import RunnableConfig

from app.core.config import get_settings
from app.core.geo import GeoRectangle
from app.core.job_log_context import append_job_log
from app.core.logger import get_logger
from app.core.region_bbox import get_region_bbox
from app.core.timeout_policy import get_timeout_policy
from app.graph.roadmap.state import RoadmapState
from app.graph.roadmap.utils import build_search_query, build_slot_key
from app.schemas.enums import Region
from app.services.google_places_service import get_google_places_service
from app.services.place_rerank_service import select_place_ids_for_day
from app.services.places_service import PlacesServiceProtocol

logger = get_logger(__name__)


def _move_selected_first(places: list[dict], selected_place_id: str) -> tuple[list[dict], bool]:
    selected_index = next(
        (index for index, place in enumerate(places) if str(place.get("place_id") or "").strip() == selected_place_id),
        None,
    )
    if selected_index in (None, 0):
        return places, False
    reordered = [places[selected_index], *places[:selected_index], *places[selected_index + 1 :]]
    return reordered, True


def _hard_filter_by_bbox(places: list, bbox: GeoRectangle) -> tuple[list, int]:
    return bbox.filter_places(places)


async def fetch_places_from_slots(
    state: RoadmapState,
    config: RunnableConfig,
) -> RoadmapState:
    """슬롯별 장소 후보를 조회해 상태에 반영합니다."""
    if state.get("error"):
        return state

    skeleton_plan = state.get("skeleton_plan")
    if not skeleton_plan:
        return {**state, "error": "fetch_places_from_slots에는 skeleton_plan이 필요합니다."}

    places_service: PlacesServiceProtocol | None = config.get("configurable", {}).get("places_service")
    if places_service is None:
        try:
            places_service = get_google_places_service()
        except Exception as exc:
            logger.error("PlacesService initialization failed: %s", exc)
            return {**state, "error": "PlacesService가 주입되지 않았습니다."}

    settings = get_settings()
    min_rating = settings.GOOGLE_PLACES_MIN_RATING
    rerank_enabled = settings.GOOGLE_PLACES_LLM_RERANK_ENABLED
    rerank_max_candidates = settings.GOOGLE_PLACES_LLM_RERANK_MAX_CANDIDATES
    rerank_timeout_seconds = get_timeout_policy(settings).llm_timeout_seconds

    fetched_places: dict[str, list] = {}

    tasks: list[tuple[str, str, Region | str | None]] = []
    for day in skeleton_plan:
        day_number = day.get("day_number", 0)
        day_region = day.get("region")
        slots = day.get("slots", [])
        for slot_index, slot in enumerate(slots):
            slot_key = build_slot_key(day_number, slot_index)
            query = build_search_query(slot)
            if query:
                tasks.append((slot_key, query, day_region))
            else:
                fetched_places[slot_key] = []

    async def search_for_slot(
        slot_key: str,
        query: str,
        region: Region | str | None,
    ) -> tuple[str, list, str]:
        geo_filter_scope = "roadmap_region"
        geo_missing_region_bbox = False
        geo_filter_fallback_unfiltered = False
        geo_filtered_out_count = 0
        fallback_stage = "restriction"
        restriction_used = False
        bias_used = False
        unfiltered_used = False

        region_bbox = get_region_bbox(region)
        if region_bbox is None:
            geo_missing_region_bbox = True

        region_label = str(region).replace("_", " ").strip() if region else ""
        geo_anchored_query = f"{region_label} {query}".strip() if region_label else query

        try:
            places = await places_service.search(
                query,
                min_rating=min_rating,
                location_restriction=region_bbox,
            )
            restriction_used = region_bbox is not None
            if region_bbox is not None and places:
                places, filtered_out = _hard_filter_by_bbox(places, region_bbox)
                geo_filtered_out_count += filtered_out

            if not places and region_bbox is not None:
                fallback_stage = "bias"
                bias_used = True
                places = await places_service.search(
                    query,
                    min_rating=min_rating,
                    location_restriction=None,
                    location_bias=region_bbox,
                )
                if places:
                    places, filtered_out = _hard_filter_by_bbox(places, region_bbox)
                    geo_filtered_out_count += filtered_out

            if not places:
                fallback_stage = "unfiltered_with_min_rating"
                geo_filter_fallback_unfiltered = True
                unfiltered_used = True
                unfiltered_results = await places_service.search(
                    geo_anchored_query,
                    min_rating=min_rating,
                )
                if unfiltered_results and region_bbox is not None:
                    places, filtered_out = _hard_filter_by_bbox(unfiltered_results, region_bbox)
                    geo_filtered_out_count += filtered_out
                else:
                    places = unfiltered_results

            if not places:
                fallback_stage = "unfiltered_without_min_rating"
                geo_filter_fallback_unfiltered = True
                unfiltered_used = True
                unfiltered_results = await places_service.search(
                    geo_anchored_query,
                    min_rating=None,
                )
                if unfiltered_results and region_bbox is not None:
                    places, filtered_out = _hard_filter_by_bbox(unfiltered_results, region_bbox)
                    geo_filtered_out_count += filtered_out
                else:
                    places = unfiltered_results

            logger.info(
                (
                    "Places search result: slot=%s min_rating_applied=%s candidate_count=%d "
                    "geo_filter_applied=%s geo_filter_scope=%s "
                    "geo_filter_fallback_unfiltered=%s geo_filtered_out_count=%d "
                    "geo_missing_region_bbox=%s fallback_stage=%s "
                    "restriction_used=%s bias_used=%s unfiltered_used=%s"
                ),
                slot_key,
                min_rating is not None,
                len(places),
                region_bbox is not None,
                geo_filter_scope,
                geo_filter_fallback_unfiltered,
                geo_filtered_out_count,
                geo_missing_region_bbox,
                fallback_stage,
                restriction_used,
                bias_used,
                unfiltered_used,
            )
            if fallback_stage != "restriction":
                append_job_log(
                    "places_search",
                    f"slot={slot_key} q={query[:40]} fb={fallback_stage} n={len(places)}",
                    level="detail",
                )
            return slot_key, [place.model_dump() for place in places], fallback_stage
        except Exception as exc:
            logger.warning("Slot place search failed: slot=%s error=%s", slot_key, exc)
            return slot_key, [], "error"

    results = await asyncio.gather(*[search_for_slot(key, query, region) for key, query, region in tasks])

    empty_count = 0
    fb_stats: dict[str, int] = {}
    for slot_key, places, fb_stage in results:
        fetched_places[slot_key] = places
        if not places:
            empty_count += 1
        fb_stats[fb_stage] = fb_stats.get(fb_stage, 0) + 1

    if rerank_enabled:

        async def rerank_for_day(day: dict) -> None:
            day_number = day.get("day_number", 0)
            slots_payload: list[dict] = []
            for slot_index, slot in enumerate(day.get("slots", [])):
                slot_key = build_slot_key(day_number, slot_index)
                candidates = fetched_places.get(slot_key, [])
                if not candidates:
                    continue
                slots_payload.append(
                    {
                        "slot_key": slot_key,
                        "section": slot.get("section"),
                        "area": slot.get("area"),
                        "keyword": slot.get("keyword"),
                        "candidates": candidates[:rerank_max_candidates],
                    }
                )

            if not slots_payload:
                return

            selected_map = await select_place_ids_for_day(
                day_number=day_number,
                slots=slots_payload,
                max_candidates=rerank_max_candidates,
                timeout_seconds=rerank_timeout_seconds,
            )
            if selected_map is None:
                logger.info(
                    (
                        "Roadmap place rerank result: flow=roadmap day=%s "
                        "batch_size=%d selected=0 missed=%d fallback_used=true"
                    ),
                    day_number,
                    len(slots_payload),
                    len(slots_payload),
                )
                return

            selected_count = 0
            missed_count = 0
            for slot in slots_payload:
                slot_key = slot["slot_key"]
                selected_place_id = selected_map.get(slot_key)
                if not selected_place_id:
                    missed_count += 1
                    continue
                selected_count += 1
                original_places = fetched_places.get(slot_key, [])
                reordered_places, _ = _move_selected_first(original_places, selected_place_id)
                fetched_places[slot_key] = reordered_places

            logger.info(
                (
                    "Roadmap place rerank result: flow=roadmap day=%s "
                    "batch_size=%d selected=%d missed=%d fallback_used=false"
                ),
                day_number,
                len(slots_payload),
                selected_count,
                missed_count,
            )

        await asyncio.gather(*[rerank_for_day(day) for day in skeleton_plan])

    fb_summary = " ".join(f"{k}={v}" for k, v in sorted(fb_stats.items()))
    append_job_log(
        "places_fetch",
        f"slots={len(fetched_places)} rerank={rerank_enabled} empty={empty_count} {fb_summary}",
    )
    logger.info("Slot place fetch completed: slot_count=%d", len(fetched_places))

    return {
        **state,
        "fetched_places": fetched_places,
    }
