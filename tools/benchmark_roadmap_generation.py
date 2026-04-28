"""Benchmark roadmap generation latency for long trips.

Run inside the application container:
    python tools/benchmark_roadmap_generation.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from app.core.job_log_context import collect_job_logs, init_job_log  # noqa: E402
from app.graph.roadmap.nodes import (  # noqa: E402
    fetch_places_from_slots,
    generate_skeleton,
    normalize_place_names,
    synthesize_final_roadmap,
)
from app.schemas.course import CourseRequest  # noqa: E402
from app.schemas.enums import (  # noqa: E402
    ActivityPreference,
    CompanionType,
    DestinationPreference,
    PacePreference,
    PlanningPreference,
    PriorityPreference,
    Region,
    TravelTheme,
)
from app.services.google_places_service import get_google_places_service  # noqa: E402

REQUIRED_ENV_KEYS = ("OPENAI_API_KEY", "GOOGLE_PLACES_API_KEY", "SERVICE_SECRET", "HMAC_SECRET")
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "roadmap-generation"
DEFAULT_CASE_TIMEOUT_SECONDS = 120


@contextmanager
def timed() -> Any:
    started = perf_counter()
    result = {"elapsed_seconds": 0.0}
    try:
        yield result
    finally:
        result["elapsed_seconds"] = round(perf_counter() - started, 3)


def _region_case(
    *,
    case_id: str,
    region: Region,
    days: int,
    start_date: date,
    companion_type: list[CompanionType],
    travel_themes: list[TravelTheme],
    pace_preference: PacePreference,
    planning_preference: PlanningPreference,
    destination_preference: DestinationPreference,
    activity_preference: ActivityPreference,
    priority_preference: PriorityPreference,
    notes: str,
) -> dict[str, Any]:
    end_date = start_date + timedelta(days=days - 1)
    request = CourseRequest.model_validate(
        {
            "start_date": start_date,
            "end_date": end_date,
            "regions": [{"region": region, "start_date": start_date, "end_date": end_date}],
            "people_count": 2,
            "companion_type": companion_type,
            "travel_themes": travel_themes,
            "pace_preference": pace_preference,
            "planning_preference": planning_preference,
            "destination_preference": destination_preference,
            "activity_preference": activity_preference,
            "priority_preference": priority_preference,
            "notes": notes,
        }
    )
    return {"case_id": case_id, "region": region.value, "days": days, "request": request}


def build_cases() -> list[dict[str, Any]]:
    base = date(2026, 6, 1)
    return [
        _region_case(
            case_id="seven_days_seoul",
            region=Region.SEOUL,
            days=7,
            start_date=base,
            companion_type=[CompanionType.FRIENDS],
            travel_themes=[TravelTheme.FOOD_TOUR, TravelTheme.CULTURE_ART],
            pace_preference=PacePreference.DENSE,
            planning_preference=PlanningPreference.PLANNED,
            destination_preference=DestinationPreference.LOCAL_EXPERIENCE,
            activity_preference=ActivityPreference.ACTIVE,
            priority_preference=PriorityPreference.EFFICIENCY,
            notes="Long urban trip focused on food, culture, and efficient movement.",
        ),
        _region_case(
            case_id="seven_days_san_francisco",
            region=Region.SAN_FRANCISCO,
            days=7,
            start_date=base + timedelta(days=10),
            companion_type=[CompanionType.COUPLE],
            travel_themes=[TravelTheme.CITY_TRIP, TravelTheme.PHOTO_SPOTS],
            pace_preference=PacePreference.DENSE,
            planning_preference=PlanningPreference.PLANNED,
            destination_preference=DestinationPreference.TOURIST_SPOTS,
            activity_preference=ActivityPreference.ACTIVE,
            priority_preference=PriorityPreference.EMOTIONAL,
            notes="Include iconic viewpoints, neighborhoods, and local dining.",
        ),
        _region_case(
            case_id="seven_days_vancouver",
            region=Region.VANCOUVER,
            days=7,
            start_date=base + timedelta(days=20),
            companion_type=[CompanionType.FAMILY],
            travel_themes=[TravelTheme.NATURE, TravelTheme.FOOD_TOUR],
            pace_preference=PacePreference.RELAXED,
            planning_preference=PlanningPreference.PLANNED,
            destination_preference=DestinationPreference.LOCAL_EXPERIENCE,
            activity_preference=ActivityPreference.REST_FOCUSED,
            priority_preference=PriorityPreference.EFFICIENCY,
            notes="Balance nature, waterfront walks, and family-friendly restaurants.",
        ),
        _region_case(
            case_id="seven_days_sydney",
            region=Region.SYDNEY,
            days=7,
            start_date=base + timedelta(days=30),
            companion_type=[CompanionType.FRIENDS],
            travel_themes=[TravelTheme.SIGHTSEEING, TravelTheme.ACTIVITY],
            pace_preference=PacePreference.DENSE,
            planning_preference=PlanningPreference.SPONTANEOUS,
            destination_preference=DestinationPreference.TOURIST_SPOTS,
            activity_preference=ActivityPreference.ACTIVE,
            priority_preference=PriorityPreference.EMOTIONAL,
            notes="Prefer beaches, landmarks, and active outdoor experiences.",
        ),
        _region_case(
            case_id="seven_days_paris",
            region=Region.PARIS,
            days=7,
            start_date=base + timedelta(days=40),
            companion_type=[CompanionType.SOLO],
            travel_themes=[TravelTheme.CULTURE_ART, TravelTheme.FOOD_TOUR],
            pace_preference=PacePreference.RELAXED,
            planning_preference=PlanningPreference.PLANNED,
            destination_preference=DestinationPreference.LOCAL_EXPERIENCE,
            activity_preference=ActivityPreference.REST_FOCUSED,
            priority_preference=PriorityPreference.EMOTIONAL,
            notes="Prioritize museums, cafes, and walkable local neighborhoods.",
        ),
        _region_case(
            case_id="eight_days_tokyo",
            region=Region.TOKYO,
            days=8,
            start_date=base + timedelta(days=50),
            companion_type=[CompanionType.FRIENDS],
            travel_themes=[TravelTheme.SHOPPING, TravelTheme.FOOD_TOUR],
            pace_preference=PacePreference.DENSE,
            planning_preference=PlanningPreference.PLANNED,
            destination_preference=DestinationPreference.LOCAL_EXPERIENCE,
            activity_preference=ActivityPreference.ACTIVE,
            priority_preference=PriorityPreference.EFFICIENCY,
            notes="Dense city itinerary with shopping, food, and distinct neighborhoods.",
        ),
        _region_case(
            case_id="eight_days_london",
            region=Region.LONDON,
            days=8,
            start_date=base + timedelta(days=60),
            companion_type=[CompanionType.FAMILY],
            travel_themes=[TravelTheme.SIGHTSEEING, TravelTheme.CULTURE_ART],
            pace_preference=PacePreference.RELAXED,
            planning_preference=PlanningPreference.PLANNED,
            destination_preference=DestinationPreference.TOURIST_SPOTS,
            activity_preference=ActivityPreference.REST_FOCUSED,
            priority_preference=PriorityPreference.EFFICIENCY,
            notes="Family itinerary with landmarks, museums, parks, and moderate pacing.",
        ),
        _region_case(
            case_id="eight_days_new_york_city",
            region=Region.NEW_YORK_CITY,
            days=8,
            start_date=base + timedelta(days=70),
            companion_type=[CompanionType.COUPLE],
            travel_themes=[TravelTheme.CITY_TRIP, TravelTheme.FOOD_TOUR],
            pace_preference=PacePreference.DENSE,
            planning_preference=PlanningPreference.SPONTANEOUS,
            destination_preference=DestinationPreference.LOCAL_EXPERIENCE,
            activity_preference=ActivityPreference.ACTIVE,
            priority_preference=PriorityPreference.EMOTIONAL,
            notes="Mix classic New York highlights with local food and evening views.",
        ),
        _region_case(
            case_id="eight_days_bangkok",
            region=Region.BANGKOK,
            days=8,
            start_date=base + timedelta(days=80),
            companion_type=[CompanionType.FRIENDS],
            travel_themes=[TravelTheme.FOOD_TOUR, TravelTheme.UNIQUE_TRIP],
            pace_preference=PacePreference.DENSE,
            planning_preference=PlanningPreference.PLANNED,
            destination_preference=DestinationPreference.LOCAL_EXPERIENCE,
            activity_preference=ActivityPreference.ACTIVE,
            priority_preference=PriorityPreference.EFFICIENCY,
            notes="Street food, markets, temples, and nightlife with efficient movement.",
        ),
        _region_case(
            case_id="eight_days_singapore",
            region=Region.SINGAPORE,
            days=8,
            start_date=base + timedelta(days=90),
            companion_type=[CompanionType.PARENTS],
            travel_themes=[TravelTheme.CITY_TRIP, TravelTheme.HEALING],
            pace_preference=PacePreference.RELAXED,
            planning_preference=PlanningPreference.PLANNED,
            destination_preference=DestinationPreference.TOURIST_SPOTS,
            activity_preference=ActivityPreference.REST_FOCUSED,
            priority_preference=PriorityPreference.EFFICIENCY,
            notes="Comfortable itinerary with gardens, waterfront, food courts, and easy transit.",
        ),
    ]


def _summarize_state(state: dict[str, Any]) -> dict[str, Any]:
    skeleton_plan = state.get("skeleton_plan") or []
    fetched_places = state.get("fetched_places") or {}
    final_roadmap = state.get("final_roadmap") or {}
    itinerary = final_roadmap.get("itinerary") or []
    return {
        "trip_days": state.get("trip_days"),
        "slot_count": sum(len(day.get("slots", [])) for day in skeleton_plan),
        "fetched_slot_count": len(fetched_places),
        "empty_place_slot_count": sum(1 for places in fetched_places.values() if not places),
        "final_place_count": sum(len(day.get("places", [])) for day in itinerary),
    }


def _missing_env_keys() -> list[str]:
    return [key for key in REQUIRED_ENV_KEYS if not os.getenv(key)]


async def run_case(case: dict[str, Any]) -> dict[str, Any]:
    request: CourseRequest = case["request"]
    job_id = f"benchmark-{case['case_id']}"
    state: dict[str, Any] = {"course_request": request.model_dump(mode="json")}
    durations: dict[str, float] = {}
    errors: list[dict[str, str]] = []

    init_job_log(job_id)
    places_service = get_google_places_service()
    config = {"configurable": {"places_service": places_service}}

    with timed() as total_timer:
        for stage_name, stage_call in (
            ("generate_skeleton", lambda current: generate_skeleton(current)),
            ("fetch_places_from_slots", lambda current: fetch_places_from_slots(current, config)),
            ("normalize_place_names", lambda current: normalize_place_names(current)),
            ("synthesize_final_roadmap", lambda current: synthesize_final_roadmap(current)),
        ):
            with timed() as stage_timer:
                try:
                    result = stage_call(state)
                    state = await result if asyncio.iscoroutine(result) else result
                except Exception as exc:  # noqa: BLE001
                    state = {**state, "error": str(exc)}
                    errors.append({"stage": stage_name, "type": type(exc).__name__, "message": str(exc)})
            durations[stage_name] = stage_timer["elapsed_seconds"]
            if state.get("error"):
                errors.append({"stage": stage_name, "type": "pipeline_error", "message": str(state["error"])})
                break

    _, logs, logged_elapsed = collect_job_logs()
    return {
        "case_id": case["case_id"],
        "region": case["region"],
        "days": case["days"],
        "status": "FAILED" if errors else "SUCCESS",
        "request": request.model_dump(mode="json"),
        "durations_seconds": durations,
        "total_seconds": total_timer["elapsed_seconds"],
        "job_log_elapsed_seconds": round(logged_elapsed, 3),
        "summary": _summarize_state(state),
        "errors": errors,
        "job_logs": logs,
    }


def _case_stub(case: dict[str, Any], status: str, errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "region": case["region"],
        "days": case["days"],
        "status": status,
        "request": case["request"].model_dump(mode="json"),
        "errors": errors or [],
    }


async def run_benchmark(output_path: Path, case_timeout_seconds: int) -> dict[str, Any]:
    missing_env = _missing_env_keys()
    started_at = datetime.now(timezone.utc).isoformat()
    cases = build_cases()

    metadata = {
        "started_at": started_at,
        "case_count": len(cases),
        "case_timeout_seconds": case_timeout_seconds,
        "required_env_present": {key: key not in missing_env for key in REQUIRED_ENV_KEYS},
        "python": sys.version,
    }

    if missing_env:
        return {
            "metadata": metadata,
            "status": "SKIPPED",
            "skip_reason": "Missing required environment variables.",
            "missing_env_keys": missing_env,
            "cases": [_case_stub(case, "SKIPPED") for case in cases],
        }

    payload: dict[str, Any] = {"metadata": metadata, "status": "RUNNING", "cases": []}
    write_artifact(payload, output_path)

    for index, case in enumerate(cases, start=1):
        print(
            f"[{index}/{len(cases)}] running {case['case_id']} ({case['days']} days, {case['region']})",
            flush=True,
        )
        try:
            result = await asyncio.wait_for(run_case(case), timeout=case_timeout_seconds)
        except asyncio.TimeoutError:
            result = _case_stub(
                case,
                "TIMEOUT",
                [
                    {
                        "stage": "case",
                        "type": "TimeoutError",
                        "message": f"Case exceeded {case_timeout_seconds} seconds.",
                    }
                ],
            )
            result["total_seconds"] = case_timeout_seconds
        payload["cases"].append(result)
        write_artifact(payload, output_path)

    payload["status"] = "COMPLETED"
    payload["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_artifact(payload, output_path)
    return payload


def write_artifact(payload: dict[str, Any], output_path: Path | None = None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = OUTPUT_DIR / f"benchmark-before-{timestamp}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark long roadmap generation latency.")
    parser.add_argument("--output", type=Path, default=None, help="Optional artifact output path.")
    parser.add_argument(
        "--case-timeout-seconds",
        type=int,
        default=int(os.getenv("BENCHMARK_CASE_TIMEOUT_SECONDS", DEFAULT_CASE_TIMEOUT_SECONDS)),
        help="Per-case timeout. Timed out cases are recorded and the benchmark continues.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = args.output
    if output_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = OUTPUT_DIR / f"benchmark-before-{timestamp}.json"
    payload = asyncio.run(run_benchmark(output_path, max(1, args.case_timeout_seconds)))
    output_path = write_artifact(payload, output_path)
    print(f"artifact={output_path}")
    print(f"status={payload.get('status')}")
    if payload.get("missing_env_keys"):
        print(f"missing_env_keys={','.join(payload['missing_env_keys'])}")


if __name__ == "__main__":
    main()
