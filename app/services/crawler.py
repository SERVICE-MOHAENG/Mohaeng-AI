import logging

import requests
import wikipedia
from bs4 import BeautifulSoup

# 로거 설정 (에러 발생 시 로그를 남김)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CityCrawler:
    def __init__(self):
        # 위키백과 언어 설정 (영어)
        wikipedia.set_lang("en")

    def get_city_info(self, city_name_or_dict):
        """
        도시 이름(문자열) 또는 설정 딕셔너리를 받아서
        위키백과 요약 + 위키트래블 여행 정보를 긁어옵니다.
        """
        # 1. 검색어 정리 (단순 문자열 vs 딕셔너리 처리)
        if isinstance(city_name_or_dict, dict):
            wiki_query = city_name_or_dict["wikipedia"]
            travel_query = city_name_or_dict["wikitravel"]
        else:
            wiki_query = city_name_or_dict
            travel_query = city_name_or_dict

        # 2. 결과 담을 그릇
        result = {"content": "", "travel_info": ""}

        # 3. 위키백과 검색 (Wikipedia)
        try:
            # auto_suggest=False: 정확한 제목 검색
            page = wikipedia.page(wiki_query, auto_suggest=False)
            result["content"] = page.summary[:2000]  # 너무 길면 2000자에서 자름
        except Exception as e:
            # 검색 실패 시 로그 남기고 빈 내용 반환
            logger.warning(f"[Wiki Error] {wiki_query}: {e}")
            result["content"] = "상세 정보가 없습니다."

        # 4. 위키트래블 크롤링 (Wikitravel)
        try:
            url = f"https://wikitravel.org/en/{travel_query}"
            response = requests.get(url, timeout=5)  # 5초 타임아웃

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                # 본문(p 태그) 내용을 긁어옴
                paragraphs = soup.find_all("p")
                # 앞부분 5문단만 가져오기
                text_content = " ".join([p.get_text() for p in paragraphs[:5]])
                result["travel_info"] = text_content[:2000]
            else:
                result["travel_info"] = "여행 가이드 정보가 없습니다."

        except Exception as e:
            logger.warning(f"[Wikitravel Error] {travel_query}: {e}")
            result["travel_info"] = "여행 가이드 정보를 가져올 수 없습니다."

        return result
