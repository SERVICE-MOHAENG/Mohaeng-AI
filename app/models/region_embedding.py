"""지역 임베딩 모델."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class RegionEmbedding(Base):
    """지역 임베딩 정보를 저장하는 SQLAlchemy 모델.

    AI 벡터 검색을 위한 최소한의 정보만 저장합니다.
    지역의 상세 정보는 백엔드 MySQL DB의 region 테이블에서 관리됩니다.
    """

    __tablename__ = "region_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    region_id = Column(UUID(as_uuid=True), unique=True, index=True, nullable=True)
    region_name = Column(String, unique=True, index=True)
    content = Column(Text)
    embedding = Column(Vector(1536))
