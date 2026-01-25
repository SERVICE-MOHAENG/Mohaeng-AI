import os

from openai import OpenAI


class EmbeddingService:
    """
    [Real] 실제 OpenAI API를 사용하는 임베딩 서비스
    Model: text-embedding-3-small (1536차원)
    """

    def __init__(self):
        # .env 파일에서 API 키 로드
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

        self.client = OpenAI(api_key=api_key)

    def get_embedding(self, text: str) -> list[float] | None:
        try:
            if not text or not text.strip():
                return None

            clean_text = text.replace("\n", " ")

            response = self.client.embeddings.create(input=clean_text, model="text-embedding-3-small")

            return response.data[0].embedding

        except Exception as e:
            print(f"⚠️ [Embedding Error] 변환 실패: {e}")
            return None
