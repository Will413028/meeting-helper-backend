import os
import mimetypes
import re
from typing import Optional
from fastapi import Response
from fastapi.responses import FileResponse


def get_audio_file_response(
    audio_path: str, range_header: Optional[str] = None
) -> Response:
    """
    Generate a FileResponse or Response for audio streaming, supporting range requests.

    Args:
        audio_path: Absolute path to the audio file.
        range_header: The 'Range' header from the request (e.g., "bytes=0-").

    Returns:
        FileResponse if no range is requested, or Response (partial content) if range is requested.
    """
    # Get file size
    file_size = os.path.getsize(audio_path)

    # Determine content type
    content_type, _ = mimetypes.guess_type(audio_path)
    if not content_type:
        # Set default content type based on file extension
        ext = os.path.splitext(audio_path)[1].lower()
        content_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".mp4": "audio/mp4",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
            ".flac": "audio/flac",
        }
        content_type = content_types.get(ext, "audio/mpeg")

    # If no range request, return the entire file
    if not range_header:
        return FileResponse(
            audio_path,
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Cache-Control": "public, max-age=3600",
            },
        )

    # Parse range request
    range_match = re.search(r"bytes=(\d+)-(\d*)", range_header)
    if not range_match:
        return FileResponse(audio_path, media_type=content_type)

    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1

    # Ensure valid range
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    content_length = end - start + 1

    # Read the requested range
    with open(audio_path, "rb") as audio_file:
        audio_file.seek(start)
        data = audio_file.read(content_length)

    # Return partial content
    return Response(
        content=data,
        status_code=206,  # Partial Content
        headers={
            "Content-Type": content_type,
            "Content-Length": str(content_length),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        },
    )
