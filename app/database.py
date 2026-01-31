import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Docker로 띄운 DB 접속 정보 (.env 파일에서 설정 필수)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL 환경 변수가 설정되지 않았습니다.")


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI 의존성 주입을 위한 데이터베이스 세션 생성기.

    이 함수는 제너레이터(generator)로, FastAPI의 Depends 시스템에 의해 호출됩니다.
    API 요청(request)이 시작될 때마다 새로운 SQLAlchemy 세션을 생성하고,
    요청 처리가 완료되면 `finally` 블록을 통해 세션을 안전하게 닫습니다.

    Yields:
        Session: 생성된 SQLAlchemy 데이터베이스 세션 객체.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
