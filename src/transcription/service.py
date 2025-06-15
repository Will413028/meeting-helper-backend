from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import insert, select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import DataResponse, PaginatedDataResponse
from src.models import Transcription
from src.transcription.schemas import (
    GetTranscriptionByTranscriptionIdResponse,
    CreateTranscriptionParams,
    GetTranscriptionResponse,
)


async def create_transcription(
    session: AsyncSession, transcription_data: CreateTranscriptionParams
):
    try:
        insert_query = insert(Transcription).values(
            task_id=transcription_data.task_id,
            transcription_title=transcription_data.transcription_title,
            filename=transcription_data.filename,
            audio_path=transcription_data.audio_path,
            srt_path=transcription_data.srt_path,
            language=transcription_data.language,
            status=transcription_data.status,
            extra_metadata=transcription_data.extra_metadata,
        )

        await session.execute(insert_query)
        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def update_transcription(session: AsyncSession, task_id: str, **kwargs) -> bool:
    """Update transcription record by task_id"""
    # Get the transcription
    try:
        result = await session.execute(select(Transcription).filter_by(task_id=task_id))
        transcription = result.scalar_one_or_none()

        if not transcription:
            return False

        # Update allowed fields
        allowed_fields = {
            "transcription_title",
            "audio_path",
            "srt_path",
            "language",
            "status",
            "progress",
            "current_step",
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

    except Exception as e:
        await session.rollback()
        raise e


async def get_transcription_by_transcription_id(
    session: AsyncSession, transcription_id: int
) -> DataResponse[GetTranscriptionByTranscriptionIdResponse]:
    query = select(
        Transcription.transcription_id,
        Transcription.transcription_title,
        Transcription.tags,
        Transcription.speaks,
        Transcription.summary,
        Transcription.transcription_text,
        Transcription.audio_duration,
        Transcription.created_at,
    ).where(Transcription.transcription_id == transcription_id)

    result = await session.execute(query)
    result = result.first()

    return DataResponse[GetTranscriptionByTranscriptionIdResponse](data=result)


async def get_transcriptions(
    session: AsyncSession,
    name: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedDataResponse[GetTranscriptionResponse]:
    query = select(
        Transcription.transcription_id,
        Transcription.transcription_title,
        Transcription.tags,
        Transcription.audio_duration,
        Transcription.created_at,
    )

    if name:
        query = query.filter(Transcription.transcription_title.like(f"%{name}%"))

    total_count = (
        await session.execute(select(func.count()).select_from(query.subquery()))
    ).scalar()

    total_pages = (total_count + page_size - 1) // page_size

    offset = (page - 1) * page_size

    results = (
        (await session.execute(query.offset(offset).limit(page_size))).mappings().all()
    )

    return PaginatedDataResponse[GetTranscriptionResponse](
        total_count=total_count,
        total_pages=total_pages,
        current_page=page,
        data=results,
    )


async def delete_transcription_by_id(
    session: AsyncSession, transcription_id: int
) -> bool:
    """Delete transcription by transcription_id"""
    result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
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
