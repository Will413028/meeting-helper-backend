from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class SpeakerBase(BaseModel):
    speaker_identifier: str
    display_name: str
    color: str = Field(pattern="^#[0-9A-Fa-f]{6}$")  # Hex color validation
    order_index: int


class SpeakerResponse(SpeakerBase):
    speaker_id: int
    transcription_id: int
    created_at: datetime
    updated_at: datetime


class TranscriptSegmentBase(BaseModel):
    sequence_number: int
    start_time: str
    end_time: str
    start_seconds: float
    end_seconds: float
    content: str
    speaker_id: Optional[int] = None


class TranscriptSegmentResponse(TranscriptSegmentBase):
    segment_id: int
    transcription_id: int
    is_edited: bool
    created_at: datetime
    updated_at: datetime


class TranscriptSegmentUpdate(BaseModel):
    content: Optional[str] = None
    speaker_id: Optional[int] = None


class TranscriptSegmentsResponse(BaseModel):
    transcription_id: int
    speakers: List[SpeakerResponse]
    segments: List[TranscriptSegmentResponse]
    total_segments: int
