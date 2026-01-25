# app/models 폴더가 없으면 생성
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, String, Text

from app.models.base import Base


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # 도시명
    country = Column(String)  # 국가 코드
    continent = Column(String)  # 대륙 정보
    description = Column(Text)  # 기본 설명
    content = Column(Text)  # 검색용 전체 텍스트

    # OpenAI 임베딩 벡터 (1536차원)
    # [권장] pgvector의 cosine_distance 성능을 위해 인덱스 추가를 고려하세요.
    # 예: HNSW, IVFFlat. 인덱스가 없으면 전체 테이블 스캔으로 동작하여 성능이 저하됩니다.
    #
    # Alembic 마이그레이션 예시:
    # op.create_index(
    #     "idx_cities_embedding",
    #     "cities",
    #     ["embedding"],
    #     postgresql_using="hnsw",
    #     postgresql_with={"m": 16, "ef_construction": 64},
    # )
    embedding = Column(Vector(1536))
