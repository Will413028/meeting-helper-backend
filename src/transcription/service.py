from datetime import datetime, timedelta
from typing import Optional
import re
import os
from sqlalchemy import insert, select, delete, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.constants import Role
from src.schemas import DataResponse, PaginatedDataResponse
from src.models import Transcription, Speaker, TranscriptSegment, User
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
            user_id=transcription_data.user_id,
            group_id=transcription_data.group_id,
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
    user: User,
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

    # TODO: 修改不要用 hardcode
    # 如果不是 group_id == 1（admin）,加上 group_id 過濾
    if user.group_id != 1:
        query = query.where(Transcription.group_id == user.group_id)

    # 根據使用者角色過濾資料
    if user.role == Role.SUPER_ADMIN:
        # Super Admin 可以看到所有資料，不需要額外過濾
        pass
    elif user.role == Role.ADMIN:
        # Admin 可以看到自己組別和一般使用者的資料，但不能看到 Super Admin 的資料
        query = query.join(User, Transcription.user_id == User.user_id).where(
            User.role != Role.SUPER_ADMIN
        )
    else:  # UserRole.USER
        # 一般使用者只能看到自己組別內的資料
        query = query.where(Transcription.group_id == user.group_id)

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
                # Update SRT file
                await update_srt_speaker_names(
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


async def update_srt_speaker_names(
    session: AsyncSession,
    transcription_id: int,
    name_changes: list[tuple[str, str]],
) -> None:
    """Update multiple speaker names in the SRT file"""

    # Get the transcription
    result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
    transcription = result.scalar_one_or_none()

    if not transcription or not transcription.srt_path:
        logger.warning(f"No transcription or SRT path found for ID {transcription_id}")
        return

    srt_path = transcription.srt_path

    # Check if SRT file exists
    if not os.path.exists(srt_path):
        logger.error(f"SRT file not found at path: {srt_path}")
        return

    try:
        # Read the SRT file
        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        original_content = srt_content
        updated_srt = srt_content

        # Apply all name changes
        for old_name, new_name in name_changes:
            logger.info(f"Attempting to replace '{old_name}' with '{new_name}' in SRT")

            # Pattern 1: Match exact name with word boundaries (for English/alphanumeric)
            pattern1 = r"\b" + re.escape(old_name) + r"\b"

            # Pattern 2: Match Chinese format like "講者4" or other CJK characters
            # This pattern looks for the name followed by common Chinese punctuation or whitespace
            pattern2 = re.escape(old_name) + r"(?=[\s，。、：；！？）」』]|$)"

            # Pattern 3: Match name preceded by common Chinese punctuation
            pattern3 = r"(?<=[\s，。、：；！？（「『])" + re.escape(old_name)

            # Try all patterns
            temp_srt = updated_srt

            # First try pattern 1 (word boundaries)
            updated_srt = re.sub(pattern1, new_name, updated_srt)

            # Then try pattern 2 (followed by Chinese punctuation)
            updated_srt = re.sub(pattern2, new_name, updated_srt)

            # Then try pattern 3 (preceded by Chinese punctuation)
            updated_srt = re.sub(pattern3, new_name, updated_srt)

            if temp_srt != updated_srt:
                logger.info(
                    f"Successfully replaced '{old_name}' with '{new_name}' in SRT"
                )
            else:
                logger.warning(f"No matches found for '{old_name}' in SRT file")

        # Only write back if there were actual changes
        if updated_srt != original_content:
            # Create backup before modifying
            backup_path = srt_path + ".backup"
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(original_content)

            # Write updated content
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(updated_srt)

            logger.info(
                f"Successfully updated SRT file for transcription {transcription_id}. "
                f"Changes made: {len(name_changes)} speaker name(s)"
            )
            logger.info(f"Backup created at: {backup_path}")
            logger.debug(f"Original SRT snippet: {original_content[:200]}")
            logger.debug(f"Updated SRT snippet: {updated_srt[:200]}")

            # Update transcription_text in database if needed
            if transcription.transcription_text:
                update_query = (
                    update(Transcription)
                    .where(Transcription.transcription_id == transcription_id)
                    .values(transcription_text=updated_srt)
                )
                await session.execute(update_query)
        else:
            logger.warning(
                f"No changes made to SRT file for transcription {transcription_id}. "
                f"Speaker names might not exist in SRT file or patterns didn't match."
            )

    except Exception as e:
        logger.error(
            f"Error updating SRT file for transcription {transcription_id}: {e}"
        )
        raise e
