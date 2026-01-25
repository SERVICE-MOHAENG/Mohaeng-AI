import logging
import urllib.parse

import requests
import wikipediaapi
from bs4 import BeautifulSoup

# 로거 설정 (에러 발생 시 로그를 남김)
logger = logging.getLogger(__name__)


class CityCrawler:
    def __init__(self):
        # 위키백과 API 초기화 (영어)
        # User-Agent 설정은 위키미디어 정책 준수를 위해 권장됨
        self.wiki_wiki = wikipediaapi.Wikipedia(
            user_agent="Mohaeng-AI/0.1 (https://github.com/SERVICE-MOHAENG/Mohaeng-AI)",
            language="en",
            extract_format=wikipediaapi.ExtractFormat.WIKI,
        )

    def get_city_info(self, city_name_or_dict):
        """
        도시 이름(문자열) 또는 설정 딕셔너리를 받아서
        위키백과 요약 + 위키트래블 여행 정보를 긁어옵니다.
        """
        # 1. 검색어 정리 (단순 문자열 vs 딕셔너리 처리)
        if isinstance(city_name_or_dict, dict):
            # 키가 없으면 다른 키를 사용하거나, 둘 다 없으면 빈 문자열을 사용
            wiki_query = city_name_or_dict.get("wikipedia") or city_name_or_dict.get("wikitravel", "")
            travel_query = city_name_or_dict.get("wikitravel") or city_name_or_dict.get("wikipedia", "")
            if not wiki_query:
                raise ValueError("검색할 도시 이름이 딕셔너리에 없습니다.")
        else:
            wiki_query = city_name_or_dict
            travel_query = city_name_or_dict

        # 2. 결과 담을 그릇
        result = {"content": "", "travel_info": ""}

        # 3. 위키백과 검색 (Wikipedia-API 사용)
        try:
            page = self.wiki_wiki.page(wiki_query)
            if page.exists():
                result["content"] = page.summary[:2000]  # 너무 길면 2000자에서 자름
            else:
                logger.warning(f"[Wiki API] 페이지를 찾을 수 없음: '{wiki_query}'")
                result["content"] = "상세 정보가 없습니다."
        except Exception as e:
            # 검색 실패 시 로그 남기고 빈 내용 반환
            logger.warning(f"[Wiki API Error] {wiki_query}: {e}")
            result["content"] = "상세 정보를 가져오는 중 오류가 발생했습니다."

        # 4. 위키트래블 크롤링 (Wikitravel)
        try:
            # URL에 포함될 수 있는 특수문자 인코딩
            encoded_query = urllib.parse.quote(travel_query, safe="")
            url = f"https://wikitravel.org/en/{encoded_query}"
            response = requests.get(url, timeout=10)  # 타임아웃 10초로 연장

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                # 본문(p 태그) 내용을 긁어옴
                paragraphs = soup.find_all("p")
                # 앞부분 5문단만 가져오기, 단어가 붙지 않게 separator 지정
                text_content = " ".join([p.get_text(separator=" ", strip=True) for p in paragraphs[:5]])
                result["travel_info"] = text_content[:2000]
            else:
                result["travel_info"] = "여행 가이드 정보가 없습니다."

        except Exception as e:
            logger.warning(f"[Wikitravel Error] {travel_query}: {e}")
            result["travel_info"] = "여행 가이드 정보를 가져올 수 없습니다."

        return result
