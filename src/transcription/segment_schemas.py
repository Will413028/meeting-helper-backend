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


class SpeakerUpdate(BaseModel):
    display_name: Optional[str] = None
    color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")


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


class MergeSegmentsRequest(BaseModel):
    segment_ids: List[int] = Field(..., min_items=2)


class SplitSegmentRequest(BaseModel):
    split_at_seconds: float = Field(..., gt=0)
    split_text_at: Optional[int] = Field(None, gt=0)


class SegmentAtTimeResponse(BaseModel):
    segment: Optional[TranscriptSegmentResponse]
    next_segment: Optional[TranscriptSegmentResponse]
    previous_segment: Optional[TranscriptSegmentResponse]


class ExportFormat(BaseModel):
    format: str = Field(..., pattern="^(srt|vtt|txt|json)$")


class BulkSegmentUpdate(BaseModel):
    segments: List[dict] = Field(
        ..., description="List of segment updates with segment_id and fields to update"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "segments": [
                        {"segment_id": 1, "content": "Updated text", "speaker_id": 2},
                        {"segment_id": 2, "content": "Another update"},
                        {"segment_id": 3, "speaker_id": 1},
                    ]
                }
            ]
        }
    }
