import socket

import requests
import requests.packages.urllib3.util.connection as urllib3_cn
from bs4 import BeautifulSoup


# [네트워크 패치] 강제로 IPv4만 사용 (DNS/속도 이슈 해결)
def allowed_gai_family():
    return socket.AF_INET


urllib3_cn.allowed_gai_family = allowed_gai_family


class CityCrawler:
    """
    도시 데이터 수집기
    - Wikipedia: API 사용 (정확한 개요)
    - Wikitravel: 웹 크롤링 (여행 팁, 분위기)
    """

    def __init__(self):
        self.wiki_api_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
        self.wikitravel_base_url = "https://wikitravel.org/en/"

        # 봇 차단 방지 헤더 (필수)
        self.headers = {"User-Agent": "Mohaeng-AI-Bot/1.0 (Target: Education/Testing)"}

    def get_wikipedia_summary(self, city_name: str) -> str:
        """[API] Wikipedia 요약 가져오기"""
        try:
            formatted_name = city_name.strip().replace(" ", "_")
            url = f"{self.wiki_api_url}{formatted_name}"

            response = requests.get(url, headers=self.headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                if data.get("type") == "disambiguation":
                    return ""
                return data.get("extract", "")
            return ""

        except Exception as e:
            print(f"   ⚠️ [Wiki Error] {city_name}: {e}")
            return ""

    def get_wikitravel_info(self, city_name: str) -> str:
        """[Crawling] Wikitravel 본문 텍스트 가져오기"""
        try:
            # URL 생성 (공백 -> 언더바)
            formatted_name = city_name.strip().replace(" ", "_")
            url = f"{self.wikitravel_base_url}{formatted_name}"

            # 크롤링 요청
            response = requests.get(url, headers=self.headers, timeout=20)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")

                # Wikitravel 본문 추출 로직
                # 'mw-parser-output' 클래스를 가진 div를 직접 찾습니다.
                content_div = soup.find("div", {"class": "mw-parser-output"})

                if content_div:
                    # div 안의 모든 문단(p)을 가져옵니다. (recursive=False 제거)
                    paragraphs = content_div.find_all("p")
                    # 빈 문단 제외하고 텍스트만 추출
                    text_list = [p.get_text().strip() for p in paragraphs if p.get_text().strip()]

                    # 상위 5개 문단만 합쳐서 반환
                    return " ".join(text_list[:5])

            return ""

        except Exception as e:
            print(f"   ⚠️ [Wikitravel Error] {city_name}: {e}")
            return ""
