from datetime import datetime, timedelta
from typing import Optional
import re
from sqlalchemy import insert, select, delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import DataResponse, PaginatedDataResponse
from src.models import Transcription, Speaker, TranscriptSegment
from src.transcription.schemas import (
    GetTranscriptionByTranscriptionIdResponse,
    CreateTranscriptionParams,
    GetTranscriptionResponse,
    UpdateTranscriptionParams,
)
from src.logger import logger


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
            audio_duration=transcription_data.audio_duration,
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
            "audio_duration",
            "summary",
            "transcription_text",
            "tags",
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
        Transcription.audio_duration,
        Transcription.created_at,
    ).where(Transcription.transcription_id == transcription_id)

    result = (await session.execute(query)).mappings().first()

    speaker_result = await session.execute(
        select(Speaker.speaker_id, Speaker.display_name)
        .filter_by(transcription_id=transcription_id)
        .order_by(Speaker.order_index)
    )
    speakers = speaker_result.mappings().all()

    data = GetTranscriptionByTranscriptionIdResponse(
        transcription_id=result.transcription_id,
        transcription_title=result.transcription_title,
        tags=result.tags,
        summary=result.summary,
        audio_duration=result.audio_duration,
        created_at=result.created_at,
        speakers=speakers,
    )

    return DataResponse[GetTranscriptionByTranscriptionIdResponse](data=data)


async def get_transcriptions(
    session: AsyncSession,
    name: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> PaginatedDataResponse[GetTranscriptionResponse]:
    query = (
        select(
            Transcription.transcription_id,
            Transcription.transcription_title,
            Transcription.tags,
            Transcription.audio_duration,
            Transcription.created_at,
        )
        .where(Transcription.status == "completed")
        .order_by(Transcription.transcription_id.desc())
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
    """Delete transcription by transcription_id along with related speakers and segments"""
    # First check if transcription exists
    result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
    transcription = result.scalar_one_or_none()

    if transcription:
        # Delete related TranscriptSegments
        await session.execute(
            delete(TranscriptSegment).where(
                TranscriptSegment.transcription_id == transcription_id
            )
        )

        # Delete related Speakers
        await session.execute(
            delete(Speaker).where(Speaker.transcription_id == transcription_id)
        )

        # Delete the transcription itself
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


async def update_transcription_api(
    session: AsyncSession,
    transcription_id: int,
    transcription_data: UpdateTranscriptionParams,
):
    try:
        # Update transcription title and tags if provided
        update_values = {}
        if transcription_data.transcription_title is not None:
            update_values["transcription_title"] = (
                transcription_data.transcription_title
            )
        if transcription_data.tags is not None:
            update_values["tags"] = transcription_data.tags

        if update_values:
            update_query = (
                update(Transcription)
                .where(Transcription.transcription_id == transcription_id)
                .values(**update_values)
            )
            await session.execute(update_query)

        # Update speaker display names if provided
        if transcription_data.speakers is not None:
            # Get current speakers to track name changes
            speaker_name_changes = []

            for speaker_info in transcription_data.speakers:
                # Get current speaker info
                result = await session.execute(
                    select(Speaker).filter_by(
                        speaker_id=speaker_info.speaker_id,
                        transcription_id=transcription_id,
                    )
                )
                current_speaker = result.scalar_one_or_none()

                if current_speaker:
                    old_name = current_speaker.display_name
                    new_name = speaker_info.display_name

                    # Track if name actually changed
                    if old_name != new_name:
                        speaker_name_changes.append((old_name, new_name))

                    # Update speaker
                    speaker_update_query = (
                        update(Speaker)
                        .where(Speaker.speaker_id == speaker_info.speaker_id)
                        .where(Speaker.transcription_id == transcription_id)
                        .values(display_name=new_name)
                    )
                    await session.execute(speaker_update_query)

            # Update summary if any speaker names changed
            if speaker_name_changes:
                await update_summary_speaker_names(
                    session=session,
                    transcription_id=transcription_id,
                    name_changes=speaker_name_changes,
                )

        await session.commit()

    except Exception as e:
        await session.rollback()
        raise e


async def update_summary_speaker_names(
    session: AsyncSession,
    transcription_id: int,
    name_changes: list[tuple[str, str]],
) -> None:
    """Update multiple speaker names in the transcription summary"""

    # Get the transcription
    result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
    transcription = result.scalar_one_or_none()

    if not transcription or not transcription.summary:
        return

    updated_summary = transcription.summary

    # Apply all name changes
    for old_name, new_name in name_changes:
        logger.info(f"Attempting to replace '{old_name}' with '{new_name}'")

        # Pattern 1: Match exact name with word boundaries (for English/alphanumeric)
        pattern1 = r"\b" + re.escape(old_name) + r"\b"

        # Pattern 2: Match Chinese format like "講者4" or other CJK characters
        # This pattern looks for the name followed by common Chinese punctuation or whitespace
        pattern2 = re.escape(old_name) + r"(?=[\s，。、：；！？）」』]|$)"

        # Pattern 3: Match name preceded by common Chinese punctuation
        pattern3 = r"(?<=[\s，。、：；！？（「『])" + re.escape(old_name)

        # Try all patterns
        temp_summary = updated_summary

        # First try pattern 1 (word boundaries)
        updated_summary = re.sub(pattern1, new_name, updated_summary)

        # Then try pattern 2 (followed by Chinese punctuation)
        updated_summary = re.sub(pattern2, new_name, updated_summary)

        # Then try pattern 3 (preceded by Chinese punctuation)
        updated_summary = re.sub(pattern3, new_name, updated_summary)

        if temp_summary != updated_summary:
            logger.info(f"Successfully replaced '{old_name}' with '{new_name}'")
        else:
            logger.warning(f"No matches found for '{old_name}' in summary")

    # Only update if there were actual changes
    if updated_summary != transcription.summary:
        update_query = (
            update(Transcription)
            .where(Transcription.transcription_id == transcription_id)
            .values(summary=updated_summary)
        )
        await session.execute(update_query)

        logger.info(
            f"Successfully updated summary for transcription {transcription_id}. "
            f"Changes made: {len(name_changes)} speaker name(s)"
        )
        logger.debug(f"Original summary snippet: {transcription.summary[:200]}")
        logger.debug(f"Updated summary snippet: {updated_summary[:200]}")
    else:
        logger.warning(
            f"No changes made to summary for transcription {transcription_id}. "
            f"Speaker names might not exist in summary or patterns didn't match."
        )
