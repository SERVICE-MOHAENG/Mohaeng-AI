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

BBOX_OVERRIDES: dict[str, tuple[float, float, float, float]] = {
    "TOKYO": (35.4816556, 139.5628986, 35.8174827, 139.9189004),
    "HAWAII": (21.2548159, -158.2805762, 21.7120060, -157.6486277),
    "CARTAGENA": (10.3000000, -75.6300000, 10.5200000, -75.4300000),
    "ATHENS": (37.8155648, 23.5748324, 38.1355648, 23.8948324),
    "CAPPADOCIA": (38.3000000, 34.6800000, 38.8000000, 35.1000000),
}

MAX_LAT_SPAN_DEG = 6.0
MAX_LNG_SPAN_DEG = 8.0
SPAN_ALLOWLIST: set[str] = {"MALDIVES", "OKINAWA_PREFECTURE"}


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


def _override_bbox(region: Region, query: str) -> BBoxResult | None:
    raw = BBOX_OVERRIDES.get(region.value)
    if raw is None:
        return None

    min_lat, min_lng, max_lat, max_lng = raw
    return BBoxResult(
        min_lat=min_lat,
        min_lng=min_lng,
        max_lat=max_lat,
        max_lng=max_lng,
        query=query,
        display_name=f"manual_override:{region.value}",
    )


def validate_coverage(mapping: dict[Region, BBoxResult]) -> list[str]:
    errors: list[str] = []
    enum_set = set(Region)
    mapping_set = set(mapping.keys())

    missing = sorted(enum_set - mapping_set, key=lambda region: region.value)
    if missing:
        errors.append("missing_regions=" + ",".join(region.value for region in missing))

    extra = sorted(mapping_set - enum_set, key=lambda region: region.value)
    if extra:
        errors.append("extra_regions=" + ",".join(region.value for region in extra))

    return errors


def validate_bbox_order(mapping: dict[Region, BBoxResult]) -> list[str]:
    errors: list[str] = []
    for region, bbox in mapping.items():
        if bbox.min_lat >= bbox.max_lat:
            errors.append(
                (f"invalid_lat_order region={region.value} min_lat={bbox.min_lat:.7f} max_lat={bbox.max_lat:.7f}")
            )
        if bbox.min_lng >= bbox.max_lng:
            errors.append(
                (f"invalid_lng_order region={region.value} min_lng={bbox.min_lng:.7f} max_lng={bbox.max_lng:.7f}")
            )
    return errors


def validate_bbox_spans(
    mapping: dict[Region, BBoxResult],
    *,
    max_lat_span_deg: float = MAX_LAT_SPAN_DEG,
    max_lng_span_deg: float = MAX_LNG_SPAN_DEG,
    allowlist: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    allowed = allowlist or SPAN_ALLOWLIST

    for region, bbox in mapping.items():
        if region.value in allowed:
            continue

        lat_span = bbox.max_lat - bbox.min_lat
        lng_span = bbox.max_lng - bbox.min_lng
        if lat_span > max_lat_span_deg or lng_span > max_lng_span_deg:
            errors.append(
                (
                    f"bbox_span_outlier region={region.value} "
                    f"lat_span={lat_span:.7f} lng_span={lng_span:.7f} "
                    f"max_lat_span={max_lat_span_deg:.1f} max_lng_span={max_lng_span_deg:.1f}"
                )
            )

    return errors


def validate_mapping(mapping: dict[Region, BBoxResult]) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_coverage(mapping))
    errors.extend(validate_bbox_order(mapping))
    errors.extend(validate_bbox_spans(mapping))
    return errors


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
            override = _override_bbox(region, query)
            if override is not None:
                resolved[region] = override
                continue

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

    validation_errors = validate_mapping(resolved)
    for message in validation_errors:
        print(f"[validation_error] {message}", file=sys.stderr)
    if validation_errors:
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
