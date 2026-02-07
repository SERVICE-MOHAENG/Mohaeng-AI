"""로드맵 생성 트리거 및 콜백 스키마."""

from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field

from app.schemas.course import CourseRequest, CourseResponse


class GenerateRequest(BaseModel):
    """NestJS가 Python 워커에 전달하는 생성 요청 모델."""

    job_id: str = Field(..., description="NestJS가 발급한 작업 ID")
    callback_url: AnyHttpUrl = Field(..., description="결과 콜백을 받을 NestJS Webhook URL")
    payload: CourseRequest = Field(..., description="로드맵 생성을 위한 요청 데이터")


class GenerateAckResponse(BaseModel):
    """Python 워커가 즉시 반환하는 수락 응답."""

    job_id: str = Field(..., description="수락된 작업 ID")
    status: str = Field("ACCEPTED", description="요청 수락 상태")


class CallbackError(BaseModel):
    """콜백 실패 시 오류 정보."""

    code: str = Field(..., description="오류 코드")
    message: str = Field(..., description="오류 메시지")


class GenerateCallbackSuccess(BaseModel):
    """성공 콜백 페이로드."""

    status: Literal["SUCCESS"] = Field("SUCCESS", description="작업 성공 상태")
    data: CourseResponse = Field(..., description="생성된 로드맵 결과")


class GenerateCallbackFailure(BaseModel):
    """실패 콜백 페이로드."""

    status: Literal["FAILED"] = Field("FAILED", description="작업 실패 상태")
    error: CallbackError = Field(..., description="실패 상세")
