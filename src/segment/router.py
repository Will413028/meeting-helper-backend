from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.logger import logger
from src.core.schemas import DataResponse
from src.segment.schemas import (
    TranscriptSegmentsResponse,
    TranscriptSegmentResponse,
    TranscriptSegmentUpdate,
)
from src.segment.service import (
    get_transcript_segments,
    update_transcript_segment,
)


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
