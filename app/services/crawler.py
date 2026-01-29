import logging
import urllib.parse

import requests
import wikipediaapi
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CityCrawler:
    """Wikipedia와 Wikitravel에서 도시 정보를 크롤링하는 서비스."""

    def __init__(self):
        """CityCrawler를 초기화하고 Wikipedia-API 클라이언트를 설정합니다."""
        self.wiki_wiki = wikipediaapi.Wikipedia(
            user_agent="Mohaeng-AI/0.1 (https://github.com/SERVICE-MOHAENG/Mohaeng-AI)",
            language="en",
            extract_format=wikipediaapi.ExtractFormat.WIKI,
        )

    def _parse_query(self, city_name_or_dict: str | dict) -> tuple[str, str]:
        """
        입력값에서 Wikipedia와 Wikitravel 검색어를 추출합니다.

        Args:
            city_name_or_dict: 도시 이름(str) 또는 {"wikipedia": "...", "wikitravel": "..."} 딕셔너리.

        Returns:
            (wiki_query, travel_query) 튜플.

        Raises:
            ValueError: 유효한 검색어가 없는 경우.
        """
        if isinstance(city_name_or_dict, dict):
            wiki_query = city_name_or_dict.get("wikipedia") or city_name_or_dict.get("wikitravel", "")
            travel_query = city_name_or_dict.get("wikitravel") or city_name_or_dict.get("wikipedia", "")
            if not wiki_query:
                raise ValueError("검색할 도시 이름이 딕셔너리에 없습니다.")
        else:
            wiki_query = city_name_or_dict
            travel_query = city_name_or_dict

        return wiki_query, travel_query

    def _fetch_wikipedia(self, query: str) -> str:
        """
        Wikipedia API를 사용하여 도시 요약 정보를 가져옵니다.

        Args:
            query: 검색할 도시 이름.

        Returns:
            Wikipedia 요약 텍스트 (최대 2000자).
        """
        try:
            page = self.wiki_wiki.page(query)
            if page.exists():
                return page.summary[:2000]
            logger.warning(f"[Wiki API] 페이지를 찾을 수 없음: '{query}'")
            return "상세 정보가 없습니다."
        except Exception as e:
            logger.warning(f"[Wiki API Error] {query}: {e}")
            return "상세 정보를 가져오는 중 오류가 발생했습니다."

    def _fetch_wikitravel(self, query: str) -> str:
        """
        Wikitravel에서 여행 정보를 크롤링합니다.

        Args:
            query: 검색할 도시 이름.

        Returns:
            Wikitravel 여행 정보 텍스트 (최대 2000자).
        """
        try:
            encoded_query = urllib.parse.quote(query, safe="")
            url = f"https://wikitravel.org/en/{encoded_query}"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                paragraphs = soup.find_all("p")
                text_content = " ".join([p.get_text(separator=" ", strip=True) for p in paragraphs[:5]])
                return text_content[:2000]
            return "여행 가이드 정보가 없습니다."
        except Exception as e:
            logger.warning(f"[Wikitravel Error] {query}: {e}")
            return "여행 가이드 정보를 가져올 수 없습니다."

    def get_city_info(self, city_name_or_dict: str | dict) -> dict[str, str]:
        """
        도시 이름으로 Wikipedia 요약과 Wikitravel 정보를 크롤링합니다.

        Args:
            city_name_or_dict: 도시 이름(str) 또는 {"wikipedia": "...", "wikitravel": "..."} 딕셔너리.

        Returns:
            {'content': Wikipedia 요약, 'travel_info': Wikitravel 정보} 딕셔너리.

        Raises:
            ValueError: 유효한 검색어가 없는 경우.
        """
        wiki_query, travel_query = self._parse_query(city_name_or_dict)

        return {
            "content": self._fetch_wikipedia(wiki_query),
            "travel_info": self._fetch_wikitravel(travel_query),
        }
