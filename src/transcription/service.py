from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import os

from sqlalchemy import insert, select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Transcription


async def save_transcription(
    session: AsyncSession,
    task_id: str,
    filename: str,
    audio_path: str,
    srt_path: str,
    language: str,
    status: str = "pending",
    extra_metadata: dict | None = None,
):
    insert_query = insert(Transcription).values(
        task_id=task_id,
        filename=filename,
        audio_path=audio_path,
        srt_path=srt_path,
        language=language,
        status=status,
        extra_metadata=extra_metadata,
    )

    await session.execute(insert_query)
    await session.commit()


async def update_transcription(session: AsyncSession, task_id: str, **kwargs) -> bool:
    """Update transcription record by task_id"""
    # Get the transcription
    result = await session.execute(select(Transcription).filter_by(task_id=task_id))
    transcription = result.scalar_one_or_none()

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

    await session.commit()
    return True


async def get_transcription(
    session: AsyncSession, task_id: str
) -> Optional[Dict[str, Any]]:
    """Get transcription by task_id"""
    result = await session.execute(select(Transcription).filter_by(task_id=task_id))
    transcription = result.scalar_one_or_none()

    if transcription:
        return _model_to_dict(transcription)
    return None


async def get_transcription_by_filename(
    session: AsyncSession, filename: str
) -> Optional[Dict[str, Any]]:
    """Get the most recent transcription for a filename"""
    result = await session.execute(
        select(Transcription)
        .filter_by(filename=filename)
        .order_by(Transcription.created_at.desc())
    )
    transcription = result.scalar_one_or_none()

    if transcription:
        return _model_to_dict(transcription)
    return None


async def list_transcriptions(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List transcriptions with pagination"""
    query = select(Transcription)

    if status:
        query = query.filter_by(status=status)

    query = query.order_by(Transcription.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    transcriptions = result.scalars().all()

    return [_model_to_dict(t) for t in transcriptions]


async def count_transcriptions(
    session: AsyncSession, status: Optional[str] = None
) -> int:
    """Count total transcriptions"""
    query = select(func.count(Transcription.transcription_id))

    if status:
        query = query.filter(Transcription.status == status)

    result = await session.execute(query)
    return result.scalar() or 0


async def delete_transcription(session: AsyncSession, task_id: str) -> bool:
    """Delete transcription by task_id"""
    result = await session.execute(select(Transcription).filter_by(task_id=task_id))
    transcription = result.scalar_one_or_none()

    if transcription:
        await session.delete(transcription)
        await session.commit()
        return True
    return False


async def cleanup_old_transcriptions(session: AsyncSession, days: int = 30) -> int:
    """Delete transcriptions older than specified days"""
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await session.execute(
        delete(Transcription).where(Transcription.created_at < cutoff_date)
    )

    await session.commit()
    return result.rowcount


async def get_disk_usage_stats(session: AsyncSession) -> Dict[str, Any]:
    """Get statistics about disk usage by transcriptions"""
    result = await session.execute(
        select(Transcription.audio_path, Transcription.srt_path).filter(
            or_(
                Transcription.audio_path.isnot(None), Transcription.srt_path.isnot(None)
            )
        )
    )
    transcriptions = result.all()

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


def _model_to_dict(transcription: Transcription) -> Dict[str, Any]:
    """Convert SQLAlchemy model to dictionary"""
    return {
        "id": transcription.transcription_id,
        "task_id": transcription.task_id,
        "filename": transcription.filename,
        "audio_path": transcription.audio_path,
        "srt_path": transcription.srt_path,
        "language": transcription.language,
        "status": transcription.status,
        "progress": getattr(transcription, "progress", None),
        "current_step": getattr(transcription, "current_step", None),
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
