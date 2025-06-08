from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Iterator
from contextlib import contextmanager
import os

from src.config import settings

# Create base class for declarative models
Base = declarative_base()

# Database URL
DATABASE_URL = f"sqlite:///{os.path.join(settings.OUTPUT_DIR, 'meeting_helper.db')}"


class Transcription(Base):
    """SQLAlchemy model for transcriptions"""

    __tablename__ = "transcriptions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, nullable=False, index=True)
    filename = Column(String, nullable=False)
    audio_path = Column(String)
    srt_path = Column(String)
    language = Column(String)
    status = Column(String, nullable=False, default="pending")
    progress = Column(Integer, default=0)
    current_step = Column(String)
    error_message = Column(Text)
    result = Column(JSON)  # Stores dict as JSON
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    estimated_completion_time = Column(DateTime)
    extra_metadata = Column(JSON)  # Stores additional info as JSON


class Database:
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database connection with SQLAlchemy"""
        self.database_url = database_url or DATABASE_URL
        self.engine = create_engine(
            self.database_url,
            connect_args={"check_same_thread": False},  # Needed for SQLite
        )
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

        # Create tables
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Iterator[Session]:
        """Context manager for database sessions"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_transcription(
        self,
        task_id: str,
        filename: str,
        audio_path: Optional[str] = None,
        srt_path: Optional[str] = None,
        language: Optional[str] = None,
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
                created_at=datetime.utcnow(),
            )
            session.add(transcription)
            session.flush()
            return transcription.id

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
