"""여행 스켈레톤 플래닝용 Pydantic 모델."""

from typing import List

from pydantic import BaseModel, Field

from app.schemas.enums import Region


class SlotIntent(BaseModel):
    """방문 슬롯 단위의 검색 의도."""

    section: str = Field(
        ...,
        description="시간대 구분 (MORNING, LUNCH, AFTERNOON, DINNER, EVENING, NIGHT 중 하나).",
    )
    area: str = Field(
        ...,
        description="도시 내 구역/동네명. 상호명은 금지.",
    )
    keyword: str = Field(
        ...,
        description="활동 또는 장소 유형 키워드. 브랜드/상호명은 금지.",
    )


class DayPlan(BaseModel):
    """일자별 스켈레톤 플랜."""

    day_number: int = Field(..., ge=1, description="1부터 시작하는 일차 번호.")
    region: Region = Field(..., description="해당 일자의 여행 지역(Region) 코드.")
    slots: List[SlotIntent] = Field(..., description="해당 일자의 슬롯 의도 목록(순서 유지).")


class SkeletonPlan(BaseModel):
    """전체 여행 스켈레톤 플랜."""

    days: List[DayPlan] = Field(..., description="일자별 플랜 목록.")
