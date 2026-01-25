import os
import sys

# 현재 폴더 경로 추가 (모듈 import용)
sys.path.append(os.getcwd())

from app.services.crawler import CityCrawler
from scripts.city_data import TARGET_CITIES


def test_crawler():
    print("🕵️ 크롤러 단위 테스트 시작...")

    crawler = CityCrawler()

    # 테스트할 도시 3개만 선정 (서울, 뉴욕, 이상한 이름 테스트용 제주)
    # 실제 TARGET_CITIES 리스트에서 인덱스로 뽑거나 직접 지정
    test_targets = [
        TARGET_CITIES[0],  # 서울 (Seoul)
        TARGET_CITIES[30],  # 뉴욕 (New York City)
        TARGET_CITIES[2],  # 제주 (Jeju City / Jeju) - 딕셔너리 구조 테스트
    ]

    for city_data in test_targets:
        korean_name = city_data["name"]

        # 1. 검색어 결정 로직 (ingest_data.py와 동일)
        from scripts.ingest_data import get_search_term

        search_term = get_search_term(korean_name)

        print(f"\n🧪 테스트 중: {korean_name} (검색어: {search_term})")

        # 2. 크롤링 실행
        try:
            result = crawler.get_city_info(search_term)

            print(f"   ✅ [Wiki] 내용 길이: {len(result['content'])}자")
            print(f"   ✅ [Travel] 내용 길이: {len(result['travel_info'])}자")

            # 내용 미리보기
            print(f"   📄 위키 내용: {result['content'][:50]}...")

        except Exception as e:
            print(f"   ❌ 실패: {e}")


if __name__ == "__main__":
    test_crawler()
