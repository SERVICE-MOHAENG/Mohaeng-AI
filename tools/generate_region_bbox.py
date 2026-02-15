"""OpenStreetMap Nominatim으로 Region -> GeoRectangle 데이터를 생성합니다.

사용법:
  python tools/generate_region_bbox.py --write app/core/region_bbox_data.py
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

import requests

from app.schemas.enums import Region

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "mohaeng-ai-region-bbox-generator/1.0 (contact: dev@localhost)"

QUERY_OVERRIDES: dict[str, str] = {
    "JEJU_CITY": "Jeju City, South Korea",
    "GYEONGJU": "Gyeongju, South Korea",
    "HOKKAIDO": "Hokkaido, Japan",
    "OKINAWA_PREFECTURE": "Okinawa Prefecture, Japan",
    "PHUKET_PROVINCE": "Phuket Province, Thailand",
    "HO_CHI_MINH_CITY": "Ho Chi Minh City, Vietnam",
    "CEBU_CITY": "Cebu City, Philippines",
    "BALI": "Bali, Indonesia",
    "MALDIVES": "Maldives",
    "NEW_YORK_CITY": "New York City, USA",
    "LOS_ANGELES": "Los Angeles, USA",
    "SAN_FRANCISCO": "San Francisco, USA",
    "LAS_VEGAS": "Las Vegas, USA",
    "HAWAII": "Hawaii, USA",
    "MEXICO_CITY": "Mexico City, Mexico",
    "RIO_DE_JANEIRO": "Rio de Janeiro, Brazil",
    "SAO_PAULO": "Sao Paulo, Brazil",
    "BUENOS_AIRES": "Buenos Aires, Argentina",
    "SAINT_PETERSBURG": "Saint Petersburg, Russia",
    "CAPPADOCIA": "Cappadocia, Turkey",
    "ABU_DHABI": "Abu Dhabi, UAE",
    "TEL_AVIV": "Tel Aviv, Israel",
    "CAPE_TOWN": "Cape Town, South Africa",
    "GOLD_COAST": "Gold Coast, Australia",
}


@dataclass(frozen=True, slots=True)
class BBoxResult:
    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float
    query: str
    display_name: str


def _region_query(region: Region) -> str:
    override = QUERY_OVERRIDES.get(region.value)
    if override:
        return override
    return region.value.replace("_", " ").title()


def _fetch_bbox(session: requests.Session, region: Region, query: str, timeout_seconds: int) -> BBoxResult | None:
    response = session.get(
        NOMINATIM_SEARCH_URL,
        params={"q": query, "format": "jsonv2", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        return None

    bbox = payload[0].get("boundingbox")
    if not bbox or len(bbox) != 4:
        return None

    min_lat = float(bbox[0])
    max_lat = float(bbox[1])
    min_lng = float(bbox[2])
    max_lng = float(bbox[3])

    return BBoxResult(
        min_lat=min_lat,
        min_lng=min_lng,
        max_lat=max_lat,
        max_lng=max_lng,
        query=query,
        display_name=str(payload[0].get("display_name") or ""),
    )


def _render_python(mapping: dict[Region, BBoxResult]) -> str:
    lines: list[str] = []
    lines.append('"""자동 생성된 Region -> GeoRectangle 매핑."""')
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from app.core.geo import GeoRectangle")
    lines.append("from app.schemas.enums import Region")
    lines.append("")
    lines.append("REGION_BBOX_MAP: dict[Region, GeoRectangle] = {")
    for region in Region:
        result = mapping[region]
        lines.append(f"    Region.{region.value}: GeoRectangle(")
        lines.append(f"        min_lat={result.min_lat:.7f},")
        lines.append(f"        min_lng={result.min_lng:.7f},")
        lines.append(f"        max_lat={result.max_lat:.7f},")
        lines.append(f"        max_lng={result.max_lng:.7f},")
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Region bbox mapping from Nominatim.")
    parser.add_argument("--write", type=str, default="", help="Write output to file path.")
    parser.add_argument("--sleep-seconds", type=float, default=0.8, help="Delay between requests.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="HTTP timeout seconds.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero when any region cannot be resolved.",
    )
    args = parser.parse_args()

    resolved: dict[Region, BBoxResult] = {}
    unresolved: dict[Region, str] = {}

    with requests.Session() as session:
        for region in Region:
            query = _region_query(region)
            try:
                result = _fetch_bbox(session=session, region=region, query=query, timeout_seconds=args.timeout_seconds)
            except Exception as exc:  # noqa: BLE001
                unresolved[region] = f"request_error:{exc}"
                result = None

            if result is None:
                unresolved.setdefault(region, "no_result_or_bbox")
            else:
                resolved[region] = result

            time.sleep(max(0.0, args.sleep_seconds))

    for region in Region:
        if region not in resolved:
            unresolved.setdefault(region, "missing_after_iteration")

    for region, reason in sorted(unresolved.items(), key=lambda item: item[0].value):
        query = _region_query(region)
        print(f"[unresolved] region={region.value} query={query} reason={reason}", file=sys.stderr)

    if unresolved and args.strict:
        return 1

    if unresolved:
        # Partial output is still useful for manual completion, but we only render fully when complete.
        if args.write:
            print(
                f"Skip writing {args.write} because {len(unresolved)} region(s) are unresolved.",
                file=sys.stderr,
            )
        return 1

    rendered = _render_python(resolved)
    if args.write:
        with open(args.write, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
