# app/models/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 스타일 Base 클래스. 모든 모델이 이 클래스를 상속합니다."""

    pass
