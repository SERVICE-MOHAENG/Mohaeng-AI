import os
import sys

import chromadb

# 현재 실행 경로를 파이썬 경로에 추가하여 모듈을 찾을 수 있게 함
sys.path.append(os.getcwd())

from app.services.crawler import CityCrawler
from app.services.embedding import EmbeddingService
from scripts.city_data import NAME_MAPPING, TARGET_CITIES


def main():
    print("🚀 데이터 적재(Ingestion) 파이프라인 시작...")

    # 1. 서비스 초기화 (크롤러 및 임베딩)
    crawler = CityCrawler()
    embedder = EmbeddingService()

    # 2. ChromaDB 설정 (로컬 파일 시스템에 영구 저장)
    # './chroma_db' 폴더에 데이터베이스 파일이 생성됩니다.
    client = chromadb.PersistentClient(path="./chroma_db")

    # 'cities'라는 이름의 컬렉션(테이블)을 생성하거나 가져옴
    collection = client.get_or_create_collection(name="cities")

    total_cities = len(TARGET_CITIES)
    print(f"📦 처리 대상 도시: 총 {total_cities}개\n")

    success_count = 0
    fail_count = 0

    for idx, city_data in enumerate(TARGET_CITIES):
        korean_name = city_data["name"]
        # 한국어 이름에 대응하는 영어 검색어 매핑 (예: 서울 -> Seoul)
        english_query = NAME_MAPPING.get(korean_name, korean_name)

        print(f"[{idx + 1}/{total_cities}] 🏙️  {korean_name} ({english_query}) 처리 중...")

        try:
            # A. 데이터 수집 (Crawling)
            # 1. 기본 설명
            desc_text = city_data.get("regionDescription", "")
            # 2. Wikipedia 요약 정보
            wiki_summary = crawler.get_wikipedia_summary(english_query)
            # 3. Wikitravel 여행 정보
            travel_info = crawler.get_wikitravel_info(english_query)

            # 검색 품질 향상을 위한 텍스트 조합
            combined_text = (
                f"도시명: {korean_name}. 기본 설명: {desc_text}. 상세 정보: {wiki_summary} 여행 가이드: {travel_info}"
            )

            # B. 임베딩 생성 (Embedding)
            # 텍스트를 벡터(숫자 리스트)로 변환
            vector = embedder.get_embedding(combined_text)

            if vector:
                # C. DB에 적재 (Upsert)
                collection.upsert(
                    ids=[str(idx)],  # 고유 식별자
                    embeddings=[vector],  # 벡터 데이터
                    documents=[combined_text],  # 원본 텍스트 (검색 결과 표출용)
                    metadatas=[
                        {
                            "name": korean_name,
                            "country": city_data["countryCode"],
                            "continent": city_data["travelRange"],
                            "budget": city_data["averageBudgetLevel"],
                        }
                    ],
                )
                print(f"   ✅ 저장 완료 (텍스트 길이: {len(combined_text)}자)")
                success_count += 1
            else:
                print("   ❌ 임베딩 생성 실패 (건너뜀)")
                fail_count += 1

        except Exception as e:
            print(f"   💥 처리 중 에러 발생: {e}")
            fail_count += 1

        print("-" * 40)

    print(f"\n🎉 전체 작업 완료! 성공: {success_count}, 실패: {fail_count}")
    print("📂 데이터는 './chroma_db' 폴더에 저장되었습니다.")


if __name__ == "__main__":
    main()
