"""Google Places API 응답을 표준화하여 저장할 Place 모델."""

from pydantic import BaseModel, Field


class PlaceGeometry(BaseModel):
    """장소 위치 좌표."""

    latitude: float = Field(..., description="위도")
    longitude: float = Field(..., description="경도")


class Place(BaseModel):
    """Google Places API에서 반환하는 장소 정보."""

    place_id: str = Field(..., description="Google Places API 고유 ID")
    name: str = Field(..., description="장소 이름")
    address: str | None = Field(default=None, description="장소 주소")
    geometry: PlaceGeometry = Field(..., description="장소 좌표 정보")
    url: str | None = Field(default=None, description="구글 맵 URL")
    types: list[str] = Field(default_factory=list, description="장소 유형 목록")
