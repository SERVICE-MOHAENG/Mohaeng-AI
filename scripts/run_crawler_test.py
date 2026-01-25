import os
import sys

# 경로 설정 - 스크립트 위치 기준으로 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.crawler import CityCrawler
from scripts.city_data import TARGET_CITIES
from scripts.ingest_data import get_search_term


def test_crawler():
    """
    CityCrawler 서비스의 단위 테스트를 수행합니다.

    미리 정의된 테스트 대상 도시 목록(서울, 뉴욕, 제주)에 대해
    크롤링이 정상적으로 작동하고, 유의미한 콘텐츠를 반환하는지 검증합니다.
    """
    print("🕵️ 크롤러 단위 테스트 시작...")

    crawler = CityCrawler()

    # 테스트할 도시 이름으로 찾기 (데이터 순서 변경에 더 강함)
    test_city_names = ["서울", "뉴욕", "제주"]
    test_targets = [c for c in TARGET_CITIES if c.get("name") in test_city_names]

    print(f"🎯 테스트 대상: {[t['name'] for t in test_targets]}")

    for city_data in test_targets:
        korean_name = city_data["name"]

        # 1. 검색어 결정 로직 (ingest_data.py와 동일)
        search_term = get_search_term(korean_name)

        print(f"\n🧪 테스트 중: {korean_name} (검색어: {search_term})")

        # 2. 크롤링 실행
        try:
            result = crawler.get_city_info(search_term)

            print(f"   ✅ [Wiki] 내용 길이: {len(result['content'])}자")
            print(f"   ✅ [Travel] 내용 길이: {len(result['travel_info'])}자")

            # 내용 미리보기
            print(f"   📄 위키 내용: {result['content'][:50]}...")
            assert len(result["content"]) > 10, "위키 내용이 너무 짧습니다."
            assert len(result["travel_info"]) > 10, "여행 정보가 너무 짧습니다."

        except Exception as e:
            print(f"   ❌ 실패: {e}")
            # 테스트 실패 처리
            raise AssertionError(f"{korean_name} 크롤링 실패") from e


if __name__ == "__main__":
    test_crawler()
    print("\n🎉 크롤러 테스트 통과!")
