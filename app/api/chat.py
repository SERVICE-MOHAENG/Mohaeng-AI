"""로드맵 대화 API."""

import json

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import require_service_secret
from app.core.logger import get_logger
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import run_chat_pipeline

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = get_logger(__name__)


def _json_example(payload: str) -> dict:
    """Swagger example에서 JSON `null` 표현을 유지하기 위한 헬퍼."""
    return json.loads(payload)


CHAT_RESPONSE_EXAMPLES = {
    "success_modification": {
        "summary": "수정 성공 (SUCCESS)",
        "description": "일정 수정이 성공적으로 완료된 경우",
        "value": {
            "status": "SUCCESS",
            "modified_itinerary": {
                "start_date": "2026-02-11",
                "end_date": "2026-02-11",
                "trip_days": 1,
                "nights": 0,
                "people_count": 2,
                "tags": ["도심", "맛집", "전시"],
                "title": "서울 당일치기 문화+미식 코스",
                "summary": "도심 전시와 식사를 균형 있게 즐기는 일정",
                "itinerary": [
                    {
                        "day_number": 1,
                        "daily_date": "2026-02-11",
                        "places": [
                            {
                                "place_name": "블루보틀 삼청",
                                "place_id": "place_id_1",
                                "address": "서울 종로구 삼청동",
                                "latitude": 37.5829,
                                "longitude": 126.9812,
                                "place_url": "https://maps.google.com/?q=bluebottle",
                                "description": "아침 커피로 가볍게 시작하기 좋은 카페입니다.",
                                "visit_sequence": 1,
                                "visit_time": "09:00",
                            },
                            {
                                "place_name": "국립현대미술관 서울관",
                                "place_id": "place_id_2",
                                "address": "서울 종로구 삼청로 30",
                                "latitude": 37.5787,
                                "longitude": 126.9809,
                                "place_url": "https://maps.google.com/?q=mmca",
                                "description": "도심에서 예술 전시를 즐길 수 있는 공간입니다.",
                                "visit_sequence": 2,
                                "visit_time": "11:00",
                            },
                        ],
                    }
                ],
            },
            "message": "요청하신 대로 1일차 2번째 장소를 교체했어요.",
            "diff_keys": ["day1_place2"],
        },
    },
    "rejected_guardrail": {
        "summary": "가드레일 반려 (REJECTED)",
        "description": "일차 변경/삭제처럼 허용되지 않은 요청인 경우",
        "value": _json_example(
            """
            {
              "status": "REJECTED",
              "modified_itinerary": null,
              "message": "일차 삭제는 지원하지 않습니다. 삭제할 장소 순서를 지정해 주세요.",
              "diff_keys": []
            }
            """
        ),
    },
    "general_chat": {
        "summary": "일반 대화 응답 (GENERAL_CHAT)",
        "description": "수정 요청이 아닌 일반 질문에 대한 응답",
        "value": _json_example(
            """
            {
              "status": "GENERAL_CHAT",
              "modified_itinerary": null,
              "message": "현재 일정은 오전 카페, 정오 전시, 저녁 식사 흐름이라 동선이 안정적입니다.",
              "diff_keys": []
            }
            """
        ),
    },
    "ask_clarification": {
        "summary": "추가 확인 필요 (ASK_CLARIFICATION)",
        "description": "요청이 모호하여 대상/순서 확인이 필요한 경우",
        "value": _json_example(
            """
            {
              "status": "ASK_CLARIFICATION",
              "modified_itinerary": null,
              "message": "삭제할 일차와 장소 순서를 함께 알려주세요. 예: '1일차 2번째 장소 삭제해줘'",
              "diff_keys": []
            }
            """
        ),
    },
}


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_service_secret)],
    responses={
        200: {
            "description": "대화 처리 결과",
            "content": {
                "application/json": {
                    "examples": CHAT_RESPONSE_EXAMPLES,
                }
            },
        }
    },
)
async def chat_roadmap(request: ChatRequest) -> ChatResponse:
    """로드맵 대화 요청을 처리하고 결과를 반환한다."""
    try:
        return await run_chat_pipeline(request)
    except Exception as exc:
        logger.error("로드맵 대화 처리 실패: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="로드맵 대화 처리에 실패했습니다.",
        ) from exc
