import os

from dotenv import load_dotenv

from app.services.embedding import EmbeddingService

# .env 파일 로드
load_dotenv()


def main():
    print("🔮 임베딩 변환 테스트 시작...")

    # API 키 확인
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ 실패: .env 파일에 OPENAI_API_KEY가 없습니다!")
        return

    service = EmbeddingService()
    text = "테스트 문장입니다."

    vector = service.get_embedding(text)

    if vector is not None:
        print(f"✅ 성공! 벡터 차원수: {len(vector)}")
        print(f"🔢 벡터 일부: {vector[:5]}...")
    else:
        print("❌ 실패: 변환된 벡터가 없습니다.")


if __name__ == "__main__":
    main()
