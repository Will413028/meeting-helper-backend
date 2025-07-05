from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db_session
from src.logger import logger
from src.schemas import DataResponse
from src.segment.schemas import (
    TranscriptSegmentsResponse,
    TranscriptSegmentResponse,
    TranscriptSegmentUpdate,
    SpeakerResponse,
    SpeakerUpdate,
    MergeSegmentsRequest,
    SplitSegmentRequest,
    SegmentAtTimeResponse,
    BulkSegmentUpdate,
)
from src.segment.service import (
    get_transcript_segments,
    update_transcript_segment,
    update_speaker,
    merge_segments,
    split_segment,
    get_segment_at_time,
    bulk_update_segments,
)
from src.transcription.export_service import export_transcript

router = APIRouter(prefix="/v1/transcription", tags=["transcript-segments"])


@router.get(
    "/{transcription_id}/segments",
    response_model=DataResponse[TranscriptSegmentsResponse],
)
async def get_segments(
    transcription_id: int,
    include_speakers: bool = Query(True, description="Include speaker information"),
    start_time: Optional[float] = Query(None, description="Start time in seconds"),
    end_time: Optional[float] = Query(None, description="End time in seconds"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get transcript segments for a transcription.

    - **include_speakers**: Include speaker information in response
    - **start_time**: Filter segments starting from this time (in seconds)
    - **end_time**: Filter segments ending before this time (in seconds)
    """
    try:
        segments = await get_transcript_segments(
            session=session,
            transcription_id=transcription_id,
            include_speakers=include_speakers,
            start_time=start_time,
            end_time=end_time,
        )
        return DataResponse(data=segments)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting transcript segments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get transcript segments",
        )


@router.put(
    "/{transcription_id}/segment/{segment_id}",
    response_model=DataResponse[TranscriptSegmentResponse],
)
async def update_segment(
    transcription_id: int,
    segment_id: int,
    update_data: Annotated[TranscriptSegmentUpdate, Body()],
    session: AsyncSession = Depends(get_db_session),
):
    """
    Update a transcript segment.

    - **content**: New text content for the segment
    - **speaker_id**: Change the speaker for this segment
    """
    try:
        updated_segment = await update_transcript_segment(
            session=session,
            transcription_id=transcription_id,
            segment_id=segment_id,
            update_data=update_data,
        )
        return DataResponse(data=updated_segment)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating segment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update segment",
        )


@router.put(
    "/{transcription_id}/speaker/{speaker_id}",
    response_model=DataResponse[SpeakerResponse],
)
async def update_speaker_info(
    transcription_id: int,
    speaker_id: int,
    update_data: Annotated[SpeakerUpdate, Body()],
    session: AsyncSession = Depends(get_db_session),
):
    """
    Update speaker information.

    - **display_name**: New display name for the speaker
    - **color**: New color (hex format) for the speaker
    """
    try:
        updated_speaker = await update_speaker(
            session=session,
            transcription_id=transcription_id,
            speaker_id=speaker_id,
            update_data=update_data,
        )
        return DataResponse(data=updated_speaker)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating speaker: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update speaker",
        )


@router.post(
    "/{transcription_id}/segments/merge",
    response_model=DataResponse[TranscriptSegmentResponse],
)
async def merge_segments_endpoint(
    transcription_id: int,
    request: Annotated[MergeSegmentsRequest, Body()],
    session: AsyncSession = Depends(get_db_session),
):
    """
    Merge multiple consecutive segments into one.

    The segments must be consecutive in the transcript.
    The merged segment will keep the speaker of the first segment.
    """
    try:
        merged_segment = await merge_segments(
            session=session,
            transcription_id=transcription_id,
            segment_ids=request.segment_ids,
        )
        return DataResponse(data=merged_segment)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error merging segments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to merge segments",
        )


@router.post(
    "/{transcription_id}/segment/{segment_id}/split",
    response_model=DataResponse[List[TranscriptSegmentResponse]],
)
async def split_segment_endpoint(
    transcription_id: int,
    segment_id: int,
    request: Annotated[SplitSegmentRequest, Body()],
    session: AsyncSession = Depends(get_db_session),
):
    """
    Split a segment into two segments.

    - **split_at_seconds**: Time point where to split (must be within segment duration)
    - **split_text_at**: Optional character position to split the text at
    """
    try:
        segment1, segment2 = await split_segment(
            session=session,
            transcription_id=transcription_id,
            segment_id=segment_id,
            split_at_seconds=request.split_at_seconds,
            split_text_at=request.split_text_at,
        )
        return DataResponse(data=[segment1, segment2])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error splitting segment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to split segment",
        )


@router.get(
    "/{transcription_id}/segment/at-time/{seconds}",
    response_model=DataResponse[SegmentAtTimeResponse],
)
async def get_segment_at_time_endpoint(
    transcription_id: int,
    seconds: float = Path(..., description="Time in seconds"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get the segment at a specific time, along with previous and next segments.

    This is useful for syncing transcript display with audio playback.
    """
    try:
        segment_info = await get_segment_at_time(
            session=session,
            transcription_id=transcription_id,
            time_seconds=seconds,
        )
        return DataResponse(data=segment_info)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting segment at time: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get segment at time",
        )


@router.put(
    "/{transcription_id}/segments/bulk-update",
    response_model=DataResponse[List[TranscriptSegmentResponse]],
)
async def bulk_update_segments_endpoint(
    transcription_id: int,
    request: Annotated[BulkSegmentUpdate, Body()],
    session: AsyncSession = Depends(get_db_session),
):
    """
    Update multiple segments in a single request.

    This is more efficient than updating segments one by one.
    Each update should include the segment_id and the fields to update.
    """
    try:
        updated_segments = await bulk_update_segments(
            session=session,
            transcription_id=transcription_id,
            updates=request.segments,
        )
        return DataResponse(data=updated_segments)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error bulk updating segments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to bulk update segments",
        )


@router.get("/{transcription_id}/export", response_model=None)
async def export_transcript_endpoint(
    transcription_id: int,
    format: str = Query(
        "srt", pattern="^(srt|vtt|txt|json)$", description="Export format"
    ),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Export the transcript in various formats.

    Supported formats:
    - **srt**: SubRip subtitle format
    - **vtt**: WebVTT subtitle format
    - **txt**: Plain text with speaker labels
    - **json**: Structured JSON format
    """
    try:
        return await export_transcript(
            session=session,
            transcription_id=transcription_id,
            format=format,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting transcript: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export transcript",
        )
