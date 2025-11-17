from sqlalchemy import String, JSON, ForeignKey, TEXT, Float, Boolean, Integer
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    DeclarativeBase,
)
from sqlalchemy.sql import false, func
from datetime import datetime
from src.constants import Role


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    account: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.group_id"))


class Group(Base):
    __tablename__ = "groups"

    group_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(15), server_default=str(Role.USER.value))
    is_uncategorized: Mapped[bool] = mapped_column(  # cspell:ignore uncategorized
        server_default=false()
    )
    description: Mapped[str] = mapped_column(String(255), nullable=True)


class Transcription(Base):
    __tablename__ = "transcriptions"

    transcription_id: Mapped[int] = mapped_column(primary_key=True)
    transcription_title: Mapped[str] = mapped_column(String(255))
    task_id: Mapped[str] = mapped_column(String(255), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    audio_path: Mapped[str] = mapped_column(String(255))
    srt_path: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result: Mapped[dict] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=True)
    completed_at: Mapped[datetime] = mapped_column(nullable=True)
    estimated_completion_time: Mapped[datetime] = mapped_column(nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, nullable=True)
    speaks: Mapped[dict] = mapped_column(JSON, nullable=True)
    audio_duration: Mapped[float] = mapped_column(nullable=True)
    summary: Mapped[str] = mapped_column(TEXT, nullable=True)
    transcription_text: Mapped[str] = mapped_column(TEXT, nullable=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.group_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    setting_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    is_auto_delete: Mapped[bool] = mapped_column(
        server_default=false()
    )  # 自動刪除30天前的檔案
    is_auto_clean: Mapped[bool] = mapped_column(
        server_default=false()
    )  # 自動清理空間，如果如果空間使用率超過80%就刪除30天前的檔案


class Speaker(Base):
    __tablename__ = "speakers"

    speaker_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transcription_id: Mapped[int] = mapped_column(
        ForeignKey("transcriptions.transcription_id", ondelete="CASCADE")
    )
    speaker_identifier: Mapped[str] = mapped_column(String(50))  # e.g., "SPEAKER_00"
    display_name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(7))  # hex color for UI
    order_index: Mapped[int] = mapped_column(Integer)  # for ordering speakers
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    segment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transcription_id: Mapped[int] = mapped_column(
        ForeignKey("transcriptions.transcription_id", ondelete="CASCADE")
    )
    speaker_id: Mapped[int] = mapped_column(
        ForeignKey("speakers.speaker_id", ondelete="SET NULL"), nullable=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer)  # order in transcript
    start_time: Mapped[str] = mapped_column(String(20))  # "00:00:02,000"
    end_time: Mapped[str] = mapped_column(String(20))  # "00:00:08,000"
    start_seconds: Mapped[float] = mapped_column(Float)  # 2.0
    end_seconds: Mapped[float] = mapped_column(Float)  # 8.0
    content: Mapped[str] = mapped_column(TEXT)
    is_edited: Mapped[bool] = mapped_column(Boolean, server_default=false())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
