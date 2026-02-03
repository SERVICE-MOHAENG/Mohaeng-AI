from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine():
    """`SQLAlchemy` 엔진을 반환한다. 최초 호출 시에만 생성되고 이후 캐싱된다."""
    return create_engine(get_settings().DATABASE_URL)


def get_session_local() -> sessionmaker[Session]:
    """`SessionLocal` 팩토리를 반환한다."""
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_db():
    """`FastAPI` 의존성 주입을 위한 데이터베이스 세션 생성기.

    이 함수는 제너레이터(generator)로, `FastAPI`의 `Depends` 시스템에 의해 호출됩니다.
    API 요청(request)이 시작될 때마다 새로운 `SQLAlchemy` 세션을 생성하고,
    요청 처리가 완료되면 `finally` 블록을 통해 세션을 안전하게 닫습니다.

    Yields:
        `Session`: 생성된 `SQLAlchemy` 데이터베이스 세션 객체.
    """
    session_local = get_session_local()
    db = session_local()
    try:
        yield db
    finally:
        db.close()
