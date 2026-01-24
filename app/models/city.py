# app/models/city.py
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# City 테이블 정의
class City(Base):
    __tablename__ = "cities"

    # 기본키 (ID)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 도시 기본 정보
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)  # 예: Seoul
    country: Mapped[str] = mapped_column(String(100), nullable=False)  # 예: South Korea

    # 검색용 텍스트 (요약본)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # 핵심: OpenAI 임베딩 벡터 (1536차원 - text-embedding-3-small 기준)
    # 인덱싱을 통해 검색 속도 향상 가능 (HNSW 등)
    search_vector: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)

    # 메타데이터 (물가, 기후, 비행시간 등 비정형 데이터 저장용)
    # 예: {"cost_index": 85, "flight_hours": 5.5, "climate": "humid continental"}
    metadata_info: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # 관리용 타임스탬프
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), server_default=func.now()
    )

    def __repr__(self):
        return f"<City(name={self.name}, country={self.country})>"
