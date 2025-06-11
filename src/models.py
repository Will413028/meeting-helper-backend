from sqlalchemy import create_engine, String, JSON
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Mapped,
    mapped_column,
)
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os
from src.constants import Role
from src.config import settings

Base = declarative_base()

DATABASE_URL = f"sqlite:///{os.path.join(settings.OUTPUT_DIR, 'meeting_helper.db')}"

# engine = create_engine(DATABASE_URL,connect_args={"check_same_thread": False}, echo=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Transcription(Base):
    __tablename__ = "transcriptions"

    transcription_id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(255), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    audio_path: Mapped[str] = mapped_column(String(255))
    srt_path: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime]
    estimated_completion_time: Mapped[datetime]
    extra_metadata: Mapped[dict] = mapped_column(JSON)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name : Mapped[str] = mapped_column(String(50), nullable=False)
    account: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[int] = mapped_column(server_default=str(Role.USER.value))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Database:
    def save_transcription(
        self,
        task_id: str,
        filename: str,
        audio_path: str,
        srt_path: str,
        language: str,
        status: str = "pending",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Save a new transcription record"""
        with self.get_session() as session:
            transcription = Transcription(
                task_id=task_id,
                filename=filename,
                audio_path=audio_path,
                srt_path=srt_path,
                language=language,
                status=status,
                extra_metadata=extra_metadata,
            )
            session.add(transcription)
            session.flush()
            return transcription.transcription_id

    def update_transcription(self, task_id: str, **kwargs) -> bool:
        """Update transcription record by task_id"""
        with self.get_session() as session:
            transcription = (
                session.query(Transcription).filter_by(task_id=task_id).first()
            )
            if not transcription:
                return False

            # Update allowed fields
            allowed_fields = {
                "audio_path",
                "srt_path",
                "language",
                "status",
                "progress",
                "current_step",
                "error_message",
                "result",
                "started_at",
                "completed_at",
                "estimated_completion_time",
                "extra_metadata",
            }

            for key, value in kwargs.items():
                if key in allowed_fields and hasattr(transcription, key):
                    setattr(transcription, key, value)

            return True

    def get_transcription(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get transcription by task_id"""
        with self.get_session() as session:
            transcription = (
                session.query(Transcription).filter_by(task_id=task_id).first()
            )
            if transcription:
                return self._model_to_dict(transcription)
            return None

    def get_transcription_by_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """Get the most recent transcription for a filename"""
        with self.get_session() as session:
            transcription = (
                session.query(Transcription)
                .filter_by(filename=filename)
                .order_by(Transcription.created_at.desc())
                .first()
            )
            if transcription:
                return self._model_to_dict(transcription)
            return None

    def list_transcriptions(
        self, limit: int = 100, offset: int = 0, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List transcriptions with pagination"""
        with self.get_session() as session:
            query = session.query(Transcription)

            if status:
                query = query.filter_by(status=status)

            transcriptions = (
                query.order_by(Transcription.created_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

            return [self._model_to_dict(t) for t in transcriptions]

    def count_transcriptions(self, status: Optional[str] = None) -> int:
        """Count total transcriptions"""
        with self.get_session() as session:
            query = session.query(func.count(Transcription.id))

            if status:
                query = query.filter(Transcription.status == status)

            return query.scalar()

    def delete_transcription(self, task_id: str) -> bool:
        """Delete transcription by task_id"""
        with self.get_session() as session:
            transcription = (
                session.query(Transcription).filter_by(task_id=task_id).first()
            )
            if transcription:
                session.delete(transcription)
                return True
            return False

    def cleanup_old_transcriptions(self, days: int = 30) -> int:
        """Delete transcriptions older than specified days"""
        with self.get_session() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            deleted_count = (
                session.query(Transcription)
                .filter(Transcription.created_at < cutoff_date)
                .delete()
            )

            return deleted_count

    def get_disk_usage_stats(self) -> Dict[str, Any]:
        """Get statistics about disk usage by transcriptions"""
        with self.get_session() as session:
            transcriptions = (
                session.query(Transcription.audio_path, Transcription.srt_path)
                .filter(
                    (Transcription.audio_path.isnot(None))
                    | (Transcription.srt_path.isnot(None))
                )
                .all()
            )

            total_size = 0
            file_count = 0

            for trans in transcriptions:
                for path in [trans.audio_path, trans.srt_path]:
                    if path and os.path.exists(path):
                        total_size += os.path.getsize(path)
                        file_count += 1

            return {
                "total_files": file_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "total_size_gb": round(total_size / (1024 * 1024 * 1024), 2),
            }

    def _model_to_dict(self, transcription: Transcription) -> Dict[str, Any]:
        """Convert SQLAlchemy model to dictionary"""
        return {
            "id": transcription.id,
            "task_id": transcription.task_id,
            "filename": transcription.filename,
            "audio_path": transcription.audio_path,
            "srt_path": transcription.srt_path,
            "language": transcription.language,
            "status": transcription.status,
            "progress": transcription.progress,
            "current_step": transcription.current_step,
            "error_message": transcription.error_message,
            "result": transcription.result,
            "created_at": transcription.created_at.isoformat()
            if transcription.created_at
            else None,
            "started_at": transcription.started_at.isoformat()
            if transcription.started_at
            else None,
            "completed_at": transcription.completed_at.isoformat()
            if transcription.completed_at
            else None,
            "estimated_completion_time": transcription.estimated_completion_time.isoformat()
            if transcription.estimated_completion_time
            else None,
            "metadata": transcription.extra_metadata,
        }


# Global database instance
db = Database()
