"""Region별 BBox 조회 유틸리티."""

from __future__ import annotations

from app.core.geo import GeoRectangle
from app.core.logger import get_logger
from app.core.region_bbox_data import REGION_BBOX_MAP
from app.schemas.enums import Region

logger = get_logger(__name__)


def get_region_bbox(region: Region | str | None) -> GeoRectangle | None:
    """Region에 해당하는 BBox를 반환합니다. 없거나 유효하지 않으면 None입니다."""
    if region is None:
        return None

    if isinstance(region, Region):
        key = region
    else:
        raw = str(region).strip()
        if not raw:
            return None
        try:
            key = Region(raw)
        except ValueError:
            logger.warning("Unknown region for bbox lookup: region=%s", raw)
            return None

    bbox = REGION_BBOX_MAP.get(key)
    if bbox is None:
        logger.warning("Region bbox missing: region=%s", key.value)
        return None
    return bbox
