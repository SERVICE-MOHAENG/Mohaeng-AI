import requests


class CityCrawler:
    """
    도시 데이터 수집기 (Wikipedia API 전용)
    """

    def __init__(self):
        self.wiki_api_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
        # [수정] 봇 차단 방지를 위한 헤더 추가 (필수)
        self.headers = {"User-Agent": "Mohaeng-AI-Bot/1.0 (Target: Education/Testing)"}

    def get_wikipedia_summary(self, city_name: str) -> str:
        try:
            # 1. URL 인코딩
            formatted_name = city_name.strip().replace(" ", "_")
            url = f"{self.wiki_api_url}{formatted_name}"

            # 2. 헤더를 포함하여 요청 (중요!)
            response = requests.get(url, headers=self.headers, timeout=10)

            # 3. 상세 디버깅 로그 (실패 원인 파악용)
            if response.status_code != 200:
                print(f"   ⚠️ [API Fail] {city_name} -> Status: {response.status_code}")
                # 404: 문서 없음, 403: 차단됨
                return ""

            data = response.json()

            if data.get("type") == "disambiguation":
                print(f"   ⚠️ [Skip] {city_name} -> 동음이의어 문서임")
                return ""

            return data.get("extract", "")

        except Exception as e:
            print(f"   💥 [Error] {city_name}: {e}")
            return ""
