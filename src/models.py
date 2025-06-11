from sqlalchemy import String, JSON
from sqlalchemy.orm import (
    declarative_base,
    Mapped,
    mapped_column,
)
from sqlalchemy.sql import func
from datetime import datetime
from src.constants import Role

Base = declarative_base()


class Transcription(Base):
    __tablename__ = "transcriptions"

    transcription_id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(255), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    audio_path: Mapped[str] = mapped_column(String(255))
    srt_path: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str] = mapped_column(String(20), nullable=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime] = mapped_column(nullable=True)
    completed_at: Mapped[datetime] = mapped_column(nullable=True)
    estimated_completion_time: Mapped[datetime] = mapped_column(nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, nullable=True)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    account: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[int] = mapped_column(server_default=str(Role.USER.value))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
