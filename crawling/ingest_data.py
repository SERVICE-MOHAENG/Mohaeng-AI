"""지역 임베딩 데이터 적재 스크립트."""

import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.logger import get_logger
from app.database import SessionLocal, engine
from app.integrations.embedding import EmbeddingService
from app.models.base import Base
from app.models.region_embedding import RegionEmbedding
from crawling.city_data import NAME_MAPPING, TARGET_CITIES
from crawling.crawler import CityCrawler

logger = get_logger(__name__)


def init_db():
    """데이터베이스를 초기화하고 `pgvector` 확장을 활성화합니다."""
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database initialization failed: %s", e)
        raise


def get_search_term(korean_name: str) -> str | dict:
    """도시의 한글 이름을 크롤링용 영문 검색어로 변환합니다."""
    return NAME_MAPPING.get(korean_name, korean_name)


def main():
    """초기 지역 데이터를 크롤링, 임베딩하여 데이터베이스에 저장합니다."""
    logger.info("Starting region embedding data ingestion")

    init_db()

    crawler = CityCrawler()
    embedder = EmbeddingService()
    db = SessionLocal()

    success_count = 0
    fail_count = 0

    logger.info("Processing %d regions", len(TARGET_CITIES))

    try:
        for idx, city_data in enumerate(TARGET_CITIES, 1):
            region_name = city_data["name"]
            search_term = get_search_term(region_name)

            logger.info("[%d/%d] Processing: %s", idx, len(TARGET_CITIES), region_name)

            try:
                existing = db.query(RegionEmbedding).filter(RegionEmbedding.region_name == region_name).first()
                if existing:
                    logger.info("Skipping: %s already exists", region_name)
                    continue

                crawled_info = crawler.get_city_info(search_term) or {}

                combined_text = (
                    f"도시명: {region_name}. "
                    f"국가: {city_data['countryCode']}. "
                    f"특징: {city_data['regionDescription']}. "
                    f"상세 정보: {crawled_info.get('content', '')} "
                    f"여행 정보: {crawled_info.get('travel_info', '')}"
                )

                vector = embedder.get_embedding(combined_text)
                if not vector:
                    logger.error("Embedding failed for: %s", region_name)
                    fail_count += 1
                    continue

                new_region = RegionEmbedding(
                    region_id=None,
                    region_name=region_name,
                    content=combined_text,
                    embedding=vector,
                )
                db.add(new_region)
                db.commit()

                logger.info("Saved: %s (ID: %d)", region_name, new_region.id)
                success_count += 1

            except Exception as e:
                logger.error("Failed to process %s: %s", region_name, e)
                db.rollback()
                fail_count += 1

    finally:
        db.close()

    logger.info("Completed: success=%d, failed=%d", success_count, fail_count)


if __name__ == "__main__":
    main()
