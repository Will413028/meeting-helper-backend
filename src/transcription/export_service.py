from typing import Dict, Any
from fastapi import HTTPException, status
from fastapi.responses import Response, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models import TranscriptSegment, Speaker, Transcription


async def export_transcript(
    session: AsyncSession, transcription_id: int, format: str
) -> Response:
    """Export transcript in various formats"""

    # Get transcription info
    trans_result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
    transcription = trans_result.scalar_one_or_none()

    if not transcription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transcription not found"
        )

    # Get all segments
    segments_result = await session.execute(
        select(TranscriptSegment)
        .filter_by(transcription_id=transcription_id)
        .order_by(TranscriptSegment.sequence_number)
    )
    segments = segments_result.scalars().all()

    if not segments:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No transcript segments found"
        )

    # Get speakers
    speakers_result = await session.execute(
        select(Speaker)
        .filter_by(transcription_id=transcription_id)
        .order_by(Speaker.order_index)
    )
    speakers = speakers_result.scalars().all()

    # Create speaker map
    speaker_map = {s.speaker_id: s for s in speakers}

    if format == "srt":
        content = export_to_srt(segments, speaker_map)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{transcription.transcription_title}.srt"'
            },
        )
    elif format == "vtt":
        content = export_to_vtt(segments, speaker_map)
        return Response(
            content=content,
            media_type="text/vtt; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{transcription.transcription_title}.vtt"'
            },
        )
    elif format == "txt":
        content = export_to_txt(segments, speaker_map)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{transcription.transcription_title}.txt"'
            },
        )
    elif format == "json":
        content = export_to_json(segments, speaker_map, transcription)
        return JSONResponse(
            content=content,
            headers={
                "Content-Disposition": f'attachment; filename="{transcription.transcription_title}.json"'
            },
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}",
        )


def export_to_srt(segments: list, speaker_map: dict) -> str:
    """Export segments to SRT format"""
    lines = []

    for i, segment in enumerate(segments, 1):
        # Sequence number
        lines.append(str(i))

        # Timestamps
        lines.append(f"{segment.start_time} --> {segment.end_time}")

        # Content with speaker
        speaker = speaker_map.get(segment.speaker_id)
        if speaker:
            lines.append(f"{speaker.display_name}: {segment.content}")
        else:
            lines.append(segment.content)

        # Empty line between entries
        lines.append("")

    return "\n".join(lines)


def export_to_vtt(segments: list, speaker_map: dict) -> str:
    """Export segments to WebVTT format"""
    lines = ["WEBVTT", ""]

    for segment in segments:
        # Timestamps (VTT uses dots instead of commas)
        start_time = segment.start_time.replace(",", ".")
        end_time = segment.end_time.replace(",", ".")
        lines.append(f"{start_time} --> {end_time}")

        # Content with speaker
        speaker = speaker_map.get(segment.speaker_id)
        if speaker:
            # VTT supports voice spans
            lines.append(f"<v {speaker.display_name}>{segment.content}</v>")
        else:
            lines.append(segment.content)

        # Empty line between entries
        lines.append("")

    return "\n".join(lines)


def export_to_txt(segments: list, speaker_map: dict) -> str:
    """Export segments to plain text format"""
    lines = []
    current_speaker_id = None

    for segment in segments:
        # Add speaker label when speaker changes
        if segment.speaker_id != current_speaker_id:
            current_speaker_id = segment.speaker_id
            speaker = speaker_map.get(segment.speaker_id)
            if speaker:
                lines.append(f"\n{speaker.display_name}:")
            else:
                lines.append("\n未知講者:")

        # Add content
        lines.append(segment.content)

    return "\n".join(lines).strip()


def export_to_json(segments: list, speaker_map: dict, transcription) -> Dict[str, Any]:
    """Export segments to JSON format"""
    return {
        "transcription": {
            "id": transcription.transcription_id,
            "title": transcription.transcription_title,
            "language": transcription.language,
            "duration": transcription.audio_duration,
            "created_at": transcription.created_at.isoformat()
            if transcription.created_at
            else None,
        },
        "speakers": [
            {
                "id": speaker.speaker_id,
                "identifier": speaker.speaker_identifier,
                "display_name": speaker.display_name,
                "color": speaker.color,
            }
            for speaker in speaker_map.values()
        ],
        "segments": [
            {
                "id": segment.segment_id,
                "sequence": segment.sequence_number,
                "speaker_id": segment.speaker_id,
                "speaker_name": speaker_map.get(segment.speaker_id).display_name
                if segment.speaker_id and segment.speaker_id in speaker_map
                else None,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "content": segment.content,
                "is_edited": segment.is_edited,
            }
            for segment in segments
        ],
        "total_segments": len(segments),
    }
