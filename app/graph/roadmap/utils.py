"""로드맵 그래프 공통 유틸리티."""


def strip_code_fence(text: str) -> str:
    """코드 펜스를 제거합니다."""
    content = (text or "").strip()
    if content.startswith("```"):
        parts = content.split("```")
        if len(parts) > 1:
            content = parts[1].strip()
            if content.startswith("json"):
                content = content[4:].strip()
    return content.strip()


def build_slot_key(day_number: int, slot_index: int) -> str:
    """슬롯 키를 생성합니다."""
    return f"day{day_number}_slot{slot_index}"


def build_search_query(slot: dict) -> str:
    """슬롯 정보로 검색어를 구성합니다."""
    area = slot.get("area", "").strip()
    keyword = slot.get("keyword", "").strip()
    return f"{area} {keyword}".strip()
