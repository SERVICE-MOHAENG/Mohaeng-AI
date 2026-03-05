"""콜백 URL 생성 공통 유틸리티."""

from __future__ import annotations


def build_callback_url(
    base_url: str,
    job_id: str,
    default_path: str,
    *,
    alias_endings: list[tuple[str, str]] | None = None,
) -> str:
    """베이스 URL과 job_id로 최종 콜백 URL을 생성합니다.

    적용 규칙 (우선순위 순):
    1. URL에 {jobId} 또는 {job_id} 포함 → 해당만 job_id로 치환 후 반환
    2. URL이 이미 default_path(job_id 치환본)로 끝남 → 그대로 반환
    2.5. URL이 이미 /{job_id}/{result_suffix} 형태로 끝남 → 그대로 반환
         (NestJS가 완성된 콜백 URL을 그대로 전달하는 경우 대응)
    3. alias_endings에 정의된 suffix로 끝남 → 해당 suffix를 치환 path로 교체
    4. 그 외 → base_url 끝 '/' 제거 후 /{default_path}(job_id 치환) 붙여 반환

    Args:
        base_url: NestJS 등에서 전달하는 콜백 베이스 URL
        job_id: 작업 ID (placeholder 치환 및 path에 사용)
        default_path: 기본 path 템플릿 (리터럴 {job_id}가 job_id로 치환됨)
            예: "itineraries/{job_id}/result"
        alias_endings: (URL이 이 suffix로 끝날 때, 이 path로 치환). 치환 문자열에 {job_id} 사용 가능.
            예: [("/surveys/callback", "/surveys/{job_id}/result")]

    Returns:
        최종 콜백 URL
    """
    base = base_url.rstrip("/")

    if "{jobId}" in base:
        return base.replace("{jobId}", job_id)
    if "{job_id}" in base:
        return base.replace("{job_id}", job_id)

    resolved_default = default_path.replace("{job_id}", job_id)

    if base.endswith("/" + resolved_default):
        return base

    result_suffix = default_path.split("/")[-1]
    if base.endswith(f"/{job_id}/{result_suffix}"):
        return base

    if alias_endings:
        for ending, replacement in alias_endings:
            if base.endswith(ending):
                path = replacement.replace("{job_id}", job_id)
                return base[: -len(ending)] + path

    return f"{base}/{resolved_default}"
