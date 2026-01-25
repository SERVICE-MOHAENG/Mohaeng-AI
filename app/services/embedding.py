import os

from openai import OpenAI


class EmbeddingService:
    """
    OpenAI API를 사용하여 텍스트에 대한 임베딩 벡터를 생성하는 서비스.

    주로 'text-embedding-3-small' 모델을 사용하여 1536차원의 벡터를 생성합니다.
    API 키는 환경 변수 'OPENAI_API_KEY'에서 로드됩니다.
    """

    def __init__(self):
        """
        EmbeddingService를 초기화합니다.

        Raises:
            RuntimeError: OPENAI_API_KEY 환경 변수가 설정되지 않은 경우.
        """
        # .env 파일에서 API 키 로드
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

        self.client = OpenAI(api_key=api_key)

    def get_embedding(self, text: str) -> list[float] | None:
        """
        주어진 텍스트에 대한 임베딩 벡터를 반환합니다.

        Args:
            text (str): 임베딩을 생성할 텍스트.

        Returns:
            list[float] | None: 생성된 임베딩 벡터. 실패 시 None을 반환합니다.
        """
        try:
            if not text or not text.strip():
                return None

            clean_text = text.replace("\n", " ")

            response = self.client.embeddings.create(input=clean_text, model="text-embedding-3-small")

            return response.data[0].embedding

        except Exception as e:
            print(f"⚠️ [Embedding Error] 변환 실패: {e}")
            return None
