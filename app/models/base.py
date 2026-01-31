# app/models/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 SQLAlchemy 모델의 기반이 되는 선언적 기본 클래스.

    이 클래스는 SQLAlchemy 2.0의 `DeclarativeBase`를 상속받아,
    프로젝트 내의 모든 데이터베이스 모델들이 공통적으로 상속받는
    중앙 집중적 기본 클래스로 사용됩니다. 이를 통해 모델들이 동일한
    메타데이터 레지스트리를 공유하게 됩니다.
    """

    pass
