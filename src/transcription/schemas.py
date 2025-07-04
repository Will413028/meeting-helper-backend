from datetime import datetime
from typing import Annotated, TypeVar

from fastapi import Query
from pydantic import BaseModel


T = TypeVar("T")


class GetUserResponse(BaseModel):
    group_name: str
    user_id: int
    account: str
    name: str

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "group_name": "開發部",
                    "user_id": 1,
                    "account": "rd1",
                    "name": "RD1",
                }
            ]
        }
    }


class GetTranscriptionsParams(BaseModel):
    page: Annotated[int, Query(ge=1)] = 1
    page_size: Annotated[int, Query(ge=1, le=100)] = 10
    name: Annotated[str | None, Query()] = None


class GetTranscriptionResponse(BaseModel):
    transcription_id: int
    transcription_title: str
    tags: list[str] | None
    audio_duration: float
    created_at: datetime


class CreateTranscriptionParams(BaseModel):
    task_id: str
    transcription_title: str
    filename: str
    audio_path: str
    srt_path: str
    language: str
    status: str
    audio_duration: float = 0.0
    extra_metadata: dict | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task_id",
                    "transcription_title": "My Transcription",
                    "filename": "filename",
                    "audio_path": "audio_path",
                    "srt_path": "srt_path",
                    "language": "language",
                    "status": "status",
                    "audio_duration": 120.5,
                    "extra_metadata": {"key": "value"},
                }
            ]
        }
    }


class GetTranscriptionByTranscriptionIdResponse(BaseModel):
    transcription_id: int
    transcription_title: str
    tags: list[str] | None
    speaks: dict | None
    summary: str | None
    transcription_text: str | None
    audio_duration: float
    created_at: datetime


class UpdateTranscriptionParams(BaseModel):
    transcription_title: str | None
    tags: list[str] | None
    speaks: list[str] | None
