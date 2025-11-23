from typing import Optional
import re
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from src.models import TranscriptSegment, Speaker, Transcription
from src.segment.schemas import (
    SpeakerResponse,
    TranscriptSegmentResponse,
    TranscriptSegmentsResponse,
    TranscriptSegmentUpdate,
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
            "#8181F3",
            "#FACC15",
            "#2FB551",
            "#4981BE",
            "#E8362C",
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

        segment.updated_at = func.now()
        await session.commit()
        await session.refresh(segment)

    return TranscriptSegmentResponse.model_validate(segment, from_attributes=True)
