"""`CityCrawler`의 기본 동작을 검증하는 테스트 스크립트."""

import os
import sys

from app.services.crawler import CityCrawler
from scripts.city_data import TARGET_CITIES
from scripts.ingest_data import get_search_term


def test_crawler():
    """`CityCrawler` 서비스의 핵심 기능에 대한 단위 테스트를 수행합니다.

    이 테스트는 미리 정의된 도시 목록(`test_city_names`)을 사용하여
    `CityCrawler.get_city_info`가 정상적으로 정보를 크롤링하는지,
    그리고 반환된 콘텐츠가 비어 있지 않은지를 검증합니다.

    테스트는 다음을 확인합니다:
    - `Wikipedia`와 `Wikitravel`에서 모두 10자 이상의 콘텐츠를 가져오는가.
    - 예외 발생 없이 크롤링 프로세스가 완료되는가.

    검색어는 `ingest_data.get_search_term` 로직을 재사용합니다. 하나의 도시라도
    크롤링에 실패하면 `AssertionError`를 발생시켜 테스트가 중단됩니다.
    """
    print("🕵️ 크롤러 단위 테스트 시작...")

    crawler = CityCrawler()

    test_city_names = ["서울", "뉴욕", "제주"]
    test_targets = [c for c in TARGET_CITIES if c.get("name") in test_city_names]

    print(f"🎯 테스트 대상: {[t['name'] for t in test_targets]}")

    for city_data in test_targets:
        korean_name = city_data["name"]

        search_term = get_search_term(korean_name)

        print(f"\n🧪 테스트 중: {korean_name} (검색어: {search_term})")

        try:
            result = crawler.get_city_info(search_term)

            print(f"   ✅ [Wiki] 내용 길이: {len(result['content'])}자")
            print(f"   ✅ [Travel] 내용 길이: {len(result['travel_info'])}자")

            print(f"   📄 위키 내용: {result['content'][:50]}...")
            assert len(result["content"]) > 10, "위키 내용이 너무 짧습니다."
            assert len(result["travel_info"]) > 10, "여행 정보가 너무 짧습니다."

        except Exception as e:
            print(f"   ❌ 실패: {e}")
            raise AssertionError(f"{korean_name} 크롤링 실패") from e


if __name__ == "__main__":
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, PROJECT_ROOT)

    test_crawler()
    print("\n🎉 크롤러 테스트 통과!")
