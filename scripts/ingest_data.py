import os
import sys

from sqlalchemy import text

# 경로 설정 - 스크립트 위치 기준으로 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine
from app.models.base import Base
from app.models.region_embedding import RegionEmbedding
from app.services.crawler import CityCrawler
from app.services.embedding import EmbeddingService
from scripts.city_data import NAME_MAPPING, TARGET_CITIES


def init_db():
    """데이터베이스를 초기화하고 pgvector 확장을 활성화합니다.

    데이터베이스에 연결하여 'vector' PostgreSQL 확장이 없는 경우 생성합니다.
    그 다음, SQLAlchemy 모델 메타데이터를 기반으로 모든 테이블을 생성합니다.
    이 함수는 데이터 수집 프로세스가 시작되기 전에 호출되어야 합니다.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        print("✅ DB 초기화 완료")
    except Exception as e:
        print(f"⚠️ DB 초기화 중 메시지: {e}")
        raise


def get_search_term(korean_name: str) -> str | dict:
    """도시의 한글 이름을 크롤링에 사용할 영문 검색어로 변환합니다.

    `scripts.city_data.NAME_MAPPING` 딕셔너리를 참조하여 한글 이름에 해당하는
    영문 검색어 또는 특별히 정의된 검색어 딕셔너리를 찾습니다. 매핑 정보가 없는
    경우, 입력된 한글 이름을 그대로 반환합니다.

    Args:
        korean_name (str): 변환할 도시의 한글 이름 (예: "서울").

    Returns:
        str | dict: 크롤링에 사용될 영문 검색어 (예: "Seoul") 또는
                    특수 검색어 딕셔너리.
    """
    return NAME_MAPPING.get(korean_name, korean_name)


def main():
    """초기 지역 데이터를 크롤링, 임베딩하여 데이터베이스에 저장합니다.

    이 스크립트는 데이터 파이프라인의 핵심 로직을 실행하는 메인 함수입니다.
    `scripts.city_data.TARGET_CITIES`에 정의된 지역 목록을 순회하며
    다음과 같은 작업을 수행합니다.

    1. 데이터베이스를 초기화합니다 (`init_db` 호출).
    2. 각 지역에 대해 크롤러와 임베딩 서비스를 사용하여 정보를 수집하고 벡터로 변환합니다.
    3. 중복 저장을 방지하기 위해 데이터베이스에 지역이 이미 존재하는지 확인합니다.
    4. 최종적으로 지역의 content와 임베딩 벡터만 'region_embeddings' 테이블에 저장합니다.

    Note:
        지역의 상세 정보(name, country, description 등)는 백엔드 MySQL DB에서 관리합니다.
        AI DB(PostgreSQL)에는 벡터 검색을 위한 최소한의 정보만 저장합니다.
    """
    print("🚀 지역 임베딩 데이터 적재 시작 (TARGET_CITIES 사용)...")

    init_db()

    crawler = CityCrawler()
    embedder = EmbeddingService()
    db = SessionLocal()

    success_count = 0
    fail_count = 0

    print(f"📦 처리 대상 지역: 총 {len(TARGET_CITIES)}개")

    try:
        for idx, city_data in enumerate(TARGET_CITIES, 1):
            region_name = city_data["name"]

            # 1. 영어 검색어 가져오기 (NAME_MAPPING 활용)
            search_term = get_search_term(region_name)

            print(f"[{idx}/{len(TARGET_CITIES)}] 🏙️  {region_name} (검색: {search_term}) 처리 중...")

            try:
                # 중복 확인 (region_name 기준)
                existing = db.query(RegionEmbedding).filter(RegionEmbedding.region_name == region_name).first()
                if existing:
                    print("   ⏭️  이미 DB에 있음. 스킵.")
                    continue

                # 2. 크롤링 (영어 검색어 사용)
                crawled_info = crawler.get_city_info(search_term) or {}

                # 3. 텍스트 조합 (임베딩 생성용)
                # 백엔드 DB의 regionDescription과 크롤링 데이터를 활용
                combined_text = (
                    f"도시명: {region_name}. "
                    f"국가: {city_data['countryCode']}. "
                    f"특징: {city_data['regionDescription']}. "
                    f"상세 정보: {crawled_info.get('content', '')} "
                    f"여행 정보: {crawled_info.get('travel_info', '')}"
                )

                # 4. 임베딩 생성
                vector = embedder.get_embedding(combined_text)
                if not vector:
                    print("   ❌ 임베딩 실패")
                    fail_count += 1
                    continue

                # 5. DB 저장 (최소한의 정보만 저장)
                # region_id는 백엔드 연동 시 추가 예정
                new_region = RegionEmbedding(
                    region_id=None,  # 백엔드 연동 시 UUID로 업데이트 예정
                    region_name=region_name,
                    content=combined_text,
                    embedding=vector,
                )
                db.add(new_region)
                db.commit()

                print(f"   ✅ 저장 완료 (ID: {new_region.id})")
                success_count += 1

            except Exception as e:
                print(f"   ⚠️ 실패: {e}")
                db.rollback()
                fail_count += 1

    finally:
        db.close()

    print(f"\n🎉 작업 완료! 성공: {success_count}, 실패: {fail_count}")


if __name__ == "__main__":
    main()
