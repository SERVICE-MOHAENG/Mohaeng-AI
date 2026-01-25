# app/models 폴더가 없으면 생성
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer, String, Text

from app.database import Base


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # 도시명
    country = Column(String)  # 국가 코드
    continent = Column(String)  # 대륙 정보
    description = Column(Text)  # 기본 설명
    content = Column(Text)  # 검색용 전체 텍스트

    # OpenAI 임베딩 벡터 (1536차원)
    embedding = Column(Vector(1536))
