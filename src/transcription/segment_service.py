from typing import List, Optional, Tuple
from datetime import datetime, timezone
import re
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from src.models import TranscriptSegment, Speaker, Transcription
from src.transcription.segment_schemas import (
    SpeakerResponse,
    TranscriptSegmentResponse,
    TranscriptSegmentsResponse,
    SpeakerUpdate,
    TranscriptSegmentUpdate,
    SegmentAtTimeResponse,
)
from src.transcription.srt_utils import parse_srt_with_speakers
from src.logger import logger


def time_to_seconds(time_str: str) -> float:
    """Convert SRT time format to seconds"""
    # Handle format: "00:00:02,000" or "00:00:02.000"
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    return 0.0


def seconds_to_time(seconds: float) -> str:
    """Convert seconds to SRT time format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    milliseconds = int((secs % 1) * 1000)
    secs = int(secs)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


async def initialize_segments_from_srt(
    session: AsyncSession, transcription_id: int
) -> bool:
    """Initialize segments and speakers from existing SRT file"""
    try:
        # Get transcription
        result = await session.execute(
            select(Transcription).filter_by(transcription_id=transcription_id)
        )
        transcription = result.scalar_one_or_none()

        if not transcription or not transcription.srt_path:
            return False

        # Parse SRT file
        parsed_data = parse_srt_with_speakers(
            transcription.srt_path, convert_to_traditional=True
        )

        if not parsed_data or not parsed_data.get("segments"):
            return False

        # Extract unique speakers
        speakers_map = {}
        speaker_colors = [
            "#6366f1",
            "#eab308",
            "#10b981",
            "#f59e0b",
            "#ef4444",
            "#8b5cf6",
        ]

        for segment in parsed_data["segments"]:
            speaker_name = segment.get("speaker", "未知講者")
            if speaker_name not in speakers_map:
                # Extract speaker number from display name if possible
                speaker_num_match = re.search(r"講者\s*(\d+)", speaker_name)
                if speaker_num_match:
                    # Use the actual speaker number from the name
                    actual_speaker_num = int(speaker_num_match.group(1))
                    speaker_identifier = f"SPEAKER_{actual_speaker_num - 1:02d}"  # Convert back to 0-based
                else:
                    # Fall back to sequential numbering
                    speaker_num = len(speakers_map)
                    speaker_identifier = f"SPEAKER_{speaker_num:02d}"

                # Create speaker
                speaker = Speaker(
                    transcription_id=transcription_id,
                    speaker_identifier=speaker_identifier,
                    display_name=speaker_name,
                    color=speaker_colors[len(speakers_map) % len(speaker_colors)],
                    order_index=len(speakers_map),
                )
                session.add(speaker)
                await session.flush()
                speakers_map[speaker_name] = speaker.speaker_id

        # Create segments
        for segment in parsed_data["segments"]:
            speaker_name = segment.get("speaker", "未知講者")
            speaker_id = speakers_map.get(speaker_name)

            start_seconds = time_to_seconds(segment["start"])
            end_seconds = (
                time_to_seconds(segment["end"])
                if segment["end"]
                else start_seconds + 5.0
            )

            transcript_segment = TranscriptSegment(
                transcription_id=transcription_id,
                speaker_id=speaker_id,
                sequence_number=segment["index"],
                start_time=segment["start"],
                end_time=segment["end"] or seconds_to_time(end_seconds),
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                content=segment["text"],
                is_edited=False,
            )
            session.add(transcript_segment)

        await session.commit()
        logger.info(
            f"Initialized {len(parsed_data['segments'])} segments for transcription {transcription_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error initializing segments from SRT: {e}")
        await session.rollback()
        return False


async def get_transcript_segments(
    session: AsyncSession,
    transcription_id: int,
    include_speakers: bool = True,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
) -> TranscriptSegmentsResponse:
    """Get transcript segments with optional time range filtering"""

    # Check if segments exist, if not, try to initialize from SRT
    segment_count_result = await session.execute(
        select(TranscriptSegment).filter_by(transcription_id=transcription_id).limit(1)
    )
    if not segment_count_result.scalar_one_or_none():
        # Try to initialize from SRT
        initialized = await initialize_segments_from_srt(session, transcription_id)
        if not initialized:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No transcript segments found and unable to initialize from SRT",
            )

    # Build query for segments
    query = select(TranscriptSegment).filter_by(transcription_id=transcription_id)

    # Apply time range filter if provided
    if start_time is not None:
        query = query.filter(TranscriptSegment.end_seconds >= start_time)
    if end_time is not None:
        query = query.filter(TranscriptSegment.start_seconds <= end_time)

    query = query.order_by(TranscriptSegment.sequence_number)

    # Execute query
    result = await session.execute(query)
    segments = result.scalars().all()

    # Get speakers if requested
    speakers = []
    if include_speakers:
        speaker_result = await session.execute(
            select(Speaker)
            .filter_by(transcription_id=transcription_id)
            .order_by(Speaker.order_index)
        )
        speakers = speaker_result.scalars().all()

    return TranscriptSegmentsResponse(
        transcription_id=transcription_id,
        speakers=[
            SpeakerResponse.model_validate(speaker, from_attributes=True)
            for speaker in speakers
        ],
        segments=[
            TranscriptSegmentResponse.model_validate(segment, from_attributes=True)
            for segment in segments
        ],
        total_segments=len(segments),
    )


async def update_transcript_segment(
    session: AsyncSession,
    transcription_id: int,
    segment_id: int,
    update_data: TranscriptSegmentUpdate,
) -> TranscriptSegmentResponse:
    """Update a single transcript segment"""

    # Get the segment
    result = await session.execute(
        select(TranscriptSegment).filter_by(
            segment_id=segment_id, transcription_id=transcription_id
        )
    )
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found"
        )

    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    if update_dict:
        for key, value in update_dict.items():
            setattr(segment, key, value)

        # Mark as edited if content was changed
        if "content" in update_dict:
            segment.is_edited = True

        segment.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(segment)

    return TranscriptSegmentResponse.model_validate(segment, from_attributes=True)


async def update_speaker(
    session: AsyncSession,
    transcription_id: int,
    speaker_id: int,
    update_data: SpeakerUpdate,
) -> SpeakerResponse:
    """Update speaker information"""

    # Get the speaker
    result = await session.execute(
        select(Speaker).filter_by(
            speaker_id=speaker_id, transcription_id=transcription_id
        )
    )
    speaker = result.scalar_one_or_none()

    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Speaker not found"
        )

    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    if update_dict:
        for key, value in update_dict.items():
            setattr(speaker, key, value)

        speaker.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(speaker)

    return SpeakerResponse.model_validate(speaker, from_attributes=True)


async def merge_segments(
    session: AsyncSession, transcription_id: int, segment_ids: List[int]
) -> TranscriptSegmentResponse:
    """Merge multiple segments into one"""

    # Get segments to merge
    result = await session.execute(
        select(TranscriptSegment)
        .filter(
            and_(
                TranscriptSegment.transcription_id == transcription_id,
                TranscriptSegment.segment_id.in_(segment_ids),
            )
        )
        .order_by(TranscriptSegment.sequence_number)
    )
    segments = result.scalars().all()

    if len(segments) != len(segment_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more segments not found",
        )

    if len(segments) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 segments required for merging",
        )

    # Check if segments are consecutive
    sequence_numbers = [s.sequence_number for s in segments]
    if sequence_numbers != list(
        range(min(sequence_numbers), max(sequence_numbers) + 1)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Segments must be consecutive",
        )

    # Merge content
    first_segment = segments[0]
    merged_content = " ".join(s.content for s in segments)

    # Update first segment with merged content
    first_segment.content = merged_content
    first_segment.end_time = segments[-1].end_time
    first_segment.end_seconds = segments[-1].end_seconds
    first_segment.is_edited = True
    first_segment.updated_at = datetime.now(timezone.utc)

    # Delete other segments
    for segment in segments[1:]:
        await session.delete(segment)

    # Update sequence numbers for remaining segments
    await session.execute(
        update(TranscriptSegment)
        .where(
            and_(
                TranscriptSegment.transcription_id == transcription_id,
                TranscriptSegment.sequence_number > segments[-1].sequence_number,
            )
        )
        .values(sequence_number=TranscriptSegment.sequence_number - (len(segments) - 1))
    )

    await session.commit()
    await session.refresh(first_segment)

    return TranscriptSegmentResponse.model_validate(first_segment, from_attributes=True)


async def split_segment(
    session: AsyncSession,
    transcription_id: int,
    segment_id: int,
    split_at_seconds: float,
    split_text_at: Optional[int] = None,
) -> Tuple[TranscriptSegmentResponse, TranscriptSegmentResponse]:
    """Split a segment into two segments"""

    # Get the segment
    result = await session.execute(
        select(TranscriptSegment).filter_by(
            segment_id=segment_id, transcription_id=transcription_id
        )
    )
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found"
        )

    # Validate split time
    if (
        split_at_seconds <= segment.start_seconds
        or split_at_seconds >= segment.end_seconds
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Split time must be within segment duration",
        )

    # Split content
    if split_text_at is not None and 0 < split_text_at < len(segment.content):
        first_content = segment.content[:split_text_at].strip()
        second_content = segment.content[split_text_at:].strip()
    else:
        # Split at middle if no text position specified
        mid_point = len(segment.content) // 2
        first_content = segment.content[:mid_point].strip()
        second_content = segment.content[mid_point:].strip()

    # Update sequence numbers for segments after this one
    await session.execute(
        update(TranscriptSegment)
        .where(
            and_(
                TranscriptSegment.transcription_id == transcription_id,
                TranscriptSegment.sequence_number > segment.sequence_number,
            )
        )
        .values(sequence_number=TranscriptSegment.sequence_number + 1)
    )

    # Update first segment
    segment.content = first_content
    segment.end_time = seconds_to_time(split_at_seconds)
    segment.end_seconds = split_at_seconds
    segment.is_edited = True
    segment.updated_at = datetime.now(timezone.utc)

    # Create second segment
    new_segment = TranscriptSegment(
        transcription_id=transcription_id,
        speaker_id=segment.speaker_id,
        sequence_number=segment.sequence_number + 1,
        start_time=seconds_to_time(split_at_seconds),
        end_time=segment.end_time,
        start_seconds=split_at_seconds,
        end_seconds=segment.end_seconds,
        content=second_content,
        is_edited=True,
    )
    session.add(new_segment)

    await session.commit()
    await session.refresh(segment)
    await session.refresh(new_segment)

    return (
        TranscriptSegmentResponse.model_validate(segment, from_attributes=True),
        TranscriptSegmentResponse.model_validate(new_segment, from_attributes=True),
    )


async def get_segment_at_time(
    session: AsyncSession, transcription_id: int, time_seconds: float
) -> SegmentAtTimeResponse:
    """Get the segment at a specific time, with previous and next segments"""

    # Get current segment
    current_result = await session.execute(
        select(TranscriptSegment).filter(
            and_(
                TranscriptSegment.transcription_id == transcription_id,
                TranscriptSegment.start_seconds <= time_seconds,
                TranscriptSegment.end_seconds >= time_seconds,
            )
        )
    )
    current_segment = current_result.scalar_one_or_none()

    response = {"segment": None, "previous_segment": None, "next_segment": None}

    if current_segment:
        response["segment"] = TranscriptSegmentResponse.model_validate(
            current_segment, from_attributes=True
        )

        # Get previous segment
        if current_segment.sequence_number > 1:
            prev_result = await session.execute(
                select(TranscriptSegment).filter_by(
                    transcription_id=transcription_id,
                    sequence_number=current_segment.sequence_number - 1,
                )
            )
            prev_segment = prev_result.scalar_one_or_none()
            if prev_segment:
                response["previous_segment"] = TranscriptSegmentResponse.model_validate(
                    prev_segment, from_attributes=True
                )

        # Get next segment
        next_result = await session.execute(
            select(TranscriptSegment).filter_by(
                transcription_id=transcription_id,
                sequence_number=current_segment.sequence_number + 1,
            )
        )
        next_segment = next_result.scalar_one_or_none()
        if next_segment:
            response["next_segment"] = TranscriptSegmentResponse.model_validate(
                next_segment, from_attributes=True
            )

    return SegmentAtTimeResponse(**response)


async def bulk_update_segments(
    session: AsyncSession, transcription_id: int, updates: List[dict]
) -> List[TranscriptSegmentResponse]:
    """Update multiple segments in a single transaction"""

    updated_segments = []

    for update_data in updates:
        segment_id = update_data.get("segment_id")
        if not segment_id:
            continue

        # Get the segment
        result = await session.execute(
            select(TranscriptSegment).filter_by(
                segment_id=segment_id, transcription_id=transcription_id
            )
        )
        segment = result.scalar_one_or_none()

        if not segment:
            continue

        # Update fields
        if "content" in update_data:
            segment.content = update_data["content"]
            segment.is_edited = True

        if "speaker_id" in update_data:
            segment.speaker_id = update_data["speaker_id"]

        segment.updated_at = datetime.now(timezone.utc)
        updated_segments.append(segment)

    await session.commit()

    # Refresh all updated segments
    for segment in updated_segments:
        await session.refresh(segment)

    return [
        TranscriptSegmentResponse.model_validate(segment, from_attributes=True)
        for segment in updated_segments
    ]
