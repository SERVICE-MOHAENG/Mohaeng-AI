from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class RegionEmbedding(Base):
    """지역 임베딩 정보를 저장하는 SQLAlchemy 모델.

    AI 벡터 검색을 위한 최소한의 정보만 저장합니다.
    지역의 상세 정보(name, country, description 등)는 백엔드 MySQL DB의
    region 테이블에서 관리됩니다.

    Attributes:
        id (int): 고유 식별자 (Auto Increment).
        region_id (UUID): 백엔드 region 테이블의 ID (FK 역할).
        region_name (str): 지역명 (백엔드 연동 전 임시 식별용).
        content (str): 임베딩 생성을 위한 원본 텍스트.
        embedding (Vector): 지역 정보로부터 생성된 1536차원 벡터.
    """

    __tablename__ = "region_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    region_id = Column(UUID(as_uuid=True), unique=True, index=True, nullable=True)
    region_name = Column(String, unique=True, index=True)  # 백엔드 연동 전 임시 식별용
    content = Column(Text)  # 임베딩 생성에 사용된 원본 텍스트

    # OpenAI 임베딩 벡터 (1536차원)
    # [권장] pgvector의 cosine_distance 성능을 위해 인덱스 추가를 고려하세요.
    # 예: HNSW, IVFFlat. 인덱스가 없으면 전체 테이블 스캔으로 동작하여 성능이 저하됩니다.
    embedding = Column(Vector(1536))
