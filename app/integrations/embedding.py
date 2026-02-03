"""`OpenAI` 임베딩 서비스."""

from openai import OpenAI

from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """`OpenAI` API를 사용하여 텍스트 임베딩 벡터를 생성하는 서비스."""

    def __init__(self):
        """`EmbeddingService`를 초기화합니다."""
        api_key = get_settings().OPENAI_API_KEY
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

        self.client = OpenAI(api_key=api_key)

    def get_embedding(self, text: str) -> list[float] | None:
        """주어진 텍스트에 대한 임베딩 벡터를 반환합니다.

        Args:
            text: 임베딩을 생성할 텍스트.

        Returns:
            생성된 임베딩 벡터. 실패 시 None.
        """
        try:
            if not text or not text.strip():
                return None

            clean_text = text.replace("\n", " ")
            response = self.client.embeddings.create(input=clean_text, model="text-embedding-3-small")
            embedding = response.data[0].embedding

            return embedding

        except Exception as e:
            logger.error("Embedding failed: %s", e)
            return None
