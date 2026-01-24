import os
import sys

# 현재 폴더를 python 경로에 추가
sys.path.append(os.getcwd())

from app.services.crawler import CityCrawler
from scripts.city_data import NAME_MAPPING, TARGET_CITIES


def main():
    crawler = CityCrawler()

    # 테스트용으로 앞부분 3개 도시만 선택 (서울, 부산, 제주)
    test_targets = TARGET_CITIES[:3]

    print(f"🚀 통합 크롤러 테스트 시작 (대상: {len(test_targets)}개 도시)\n")

    for city_data in test_targets:
        korean_name = city_data["name"]
        mapping = NAME_MAPPING.get(korean_name, korean_name)

        if isinstance(mapping, dict):
            wiki_query = mapping.get("wikipedia", korean_name)
            travel_query = mapping.get("wikitravel", korean_name)
            print(f"🏙️  Target: {korean_name} (Wiki: {wiki_query}, Travel: {travel_query})")
        else:
            wiki_query = mapping
            travel_query = mapping
            print(f"🏙️  Target: {korean_name} ({wiki_query})")

        # 1. Wikipedia API 테스트
        wiki_text = crawler.get_wikipedia_summary(wiki_query)
        wiki_status = f"✅ 성공 ({len(wiki_text)}자)" if wiki_text else "❌ 실패"
        print(f"   [Wikipedia]   {wiki_status}")

        # 2. Wikitravel 크롤링 테스트
        travel_text = crawler.get_wikitravel_info(travel_query)
        travel_status = f"✅ 성공 ({len(travel_text)}자)" if travel_text else "❌ 실패 (데이터 없음)"
        print(f"   [Wikitravel]  {travel_status}")

        print("-" * 40)


if __name__ == "__main__":
    main()
