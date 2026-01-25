import os
import sys

from sqlalchemy import text

# 경로 설정 - 스크립트 위치 기준으로 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine
from app.models.base import Base
from app.models.city import City
from app.services.crawler import CityCrawler
from app.services.embedding import EmbeddingService

# 님이 가진 파일에서 데이터 가져오기 (변수명 맞춤)
from scripts.city_data import NAME_MAPPING, TARGET_CITIES


def init_db():
    """
    데이터베이스를 초기화하고 필요한 pgvector 확장을 활성화합니다.

    - `vector` PostgreSQL 확장이 없는 경우 생성합니다.
    - SQLAlchemy 모델 메타데이터를 기반으로 모든 테이블을 생성합니다.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        print("✅ DB 초기화 완료")
    except Exception as e:
        print(f"⚠️ DB 초기화 중 메시지: {e}")


def get_search_term(korean_name: str) -> str | dict:
    """
    도시의 한글 이름을 영문 검색어로 변환합니다.

    `NAME_MAPPING` 딕셔너리를 참조하여 한글 이름에 해당하는 영문 검색어를 찾습니다.
    매핑 정보가 없는 경우, 원본 한글 이름을 그대로 반환합니다.

    Args:
        korean_name (str): 변환할 도시의 한글 이름.

    Returns:
        str | dict: 변환된 영문 검색어 또는 검색어 설정 딕셔너리.
    """
    return NAME_MAPPING.get(korean_name, korean_name)


def main():
    """
    데이터 수집 및 임베딩 파이프라인의 메인 실행 함수.

    이 스크립트는 다음 순서로 작업을 수행합니다:
    1. `TARGET_CITIES` 목록의 각 도시에 대해 순차적으로 처리합니다.
    2. 데이터베이스에 이미 도시 정보가 있는지 확인하고, 있으면 건너뜁니다.
    3. `CityCrawler`를 사용하여 Wikipedia, Wikitravel에서 도시 정보를 크롤링합니다.
    4. `EmbeddingService`를 사용하여 수집된 텍스트 정보의 임베딩 벡터를 생성합니다.
    5. 최종적으로 도시 정보와 임베딩 벡터를 데이터베이스의 `cities` 테이블에 저장합니다.
    """
    print("🚀 고품질 데이터 적재 시작 (TARGET_CITIES 사용)...")

    init_db()

    crawler = CityCrawler()
    embedder = EmbeddingService()
    db = SessionLocal()

    success_count = 0
    fail_count = 0

    print(f"📦 처리 대상 도시: 총 {len(TARGET_CITIES)}개")

    try:
        for idx, city_data in enumerate(TARGET_CITIES, 1):
            korean_name = city_data["name"]

            # 1. 영어 검색어 가져오기 (NAME_MAPPING 활용)
            search_term = get_search_term(korean_name)

            # 크롤러가 문자열과 딕셔너리 모두 처리 가능
            crawl_target = search_term

            print(f"[{idx}/{len(TARGET_CITIES)}] 🏙️  {korean_name} (검색: {crawl_target}) 처리 중...")

            try:
                # 중복 확인
                existing = db.query(City).filter(City.name == korean_name).first()
                if existing:
                    print("   ⏭️  이미 DB에 있음. 스킵.")
                    continue

                # 2. 크롤링 (영어 검색어 사용)
                # city_data에 있는 regionDescription을 우선 사용하고, 크롤링 데이터는 보강용으로 씀
                crawled_info = crawler.get_city_info(crawl_target)

                # 3. 텍스트 조합 (기존 데이터 + 크롤링 데이터)
                # 님의 파일에 있는 좋은 설명(regionDescription)을 적극 활용
                combined_text = (
                    f"도시명: {korean_name}. "
                    f"국가: {city_data['countryCode']}. "
                    f"특징: {city_data['regionDescription']}. "
                    f"상세 정보: {crawled_info['content']} "
                    f"여행 정보: {crawled_info['travel_info']}"
                )

                # 4. 임베딩 생성
                vector = embedder.get_embedding(combined_text)
                if not vector:
                    print("   ❌ 임베딩 실패")
                    fail_count += 1
                    continue

                # 5. DB 저장
                # TARGET_CITIES에 있는 알찬 정보들을 DB에 같이 넣음
                new_city = City(
                    name=korean_name,  # 한글 이름
                    country=city_data["countryCode"],
                    continent=city_data["travelRange"],  # 여행 범위(거리) 정보
                    description=city_data["regionDescription"],  # 님이 작성한 고퀄 설명
                    content=combined_text,
                    embedding=vector,
                )
                db.add(new_city)
                db.commit()

                print(f"   ✅ 저장 완료 (ID: {new_city.id})")
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
