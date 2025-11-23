import os
import re
import shutil
import zipfile
import tempfile
import mimetypes
from pathlib import Path
from typing import Annotated, Optional
from fastapi import (
    APIRouter,
    Depends,
    Query,
    File,
    Body,
    HTTPException,
    UploadFile,
    status,
    BackgroundTasks,
    Header,
    Response,
    Form,
)
from fastapi.responses import FileResponse
from pydub import AudioSegment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.dependencies import get_current_user
from src.database import get_db_session
from src.logger import logger
from src.models import Transcription, User
from src.task_manager import task_manager
from src.config import settings
from src.transcription.service import (
    create_transcription,
    get_transcription_by_transcription_id,
    delete_transcription_by_id,
    get_transcriptions,
    update_transcription_api,
)
from src.group.service import get_super_admin_group_id
from src.transcription.schemas import (
    CreateTranscriptionParams,
    GetTranscriptionsParams,
    GetTranscriptionByTranscriptionIdResponse,
    GetTranscriptionResponse,
    UpdateTranscriptionParams,
)
from src.transcription.audio_utils import get_audio_duration
from src.schemas import PaginatedDataResponse, DataResponse, DetailResponse
from src.transcription.background_processor import queue_audio_processing
from src.constants import Role

router = APIRouter(tags=["transcription"])


@router.post("/v1/transcribe")
async def _transcribe_audio(
    current_user: Annotated[User, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form(default="zh"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Upload an audio file and start async transcription with progress tracking

    Returns task_id to track progress
    """
    # Validate file extension
    allowed_extensions = [
        ".mp3",
        ".wav",
        ".mp4",
        ".m4a",
        ".flac",
        ".ogg",
        ".webm",
        ".mov",
    ]
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}",
        )

    # Create task
    task_id = task_manager.create_task(
        filename=file.filename, group_id=current_user.group_id
    )

    # Save uploaded file to a temporary location first
    temp_file = None
    try:
        # Create a temporary file to save the uploaded content
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=file_extension
        ) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = temp_file.name

        # Convert to MP3
        logger.info(f"Converting {file.filename} to MP3 format")

        # Load the audio file
        audio = AudioSegment.from_file(temp_path)

        # Set up MP3 output path
        mp3_filename = f"{task_id}_{Path(file.filename).stem}.mp3"
        audio_path = os.path.join(settings.OUTPUT_DIR, mp3_filename)

        # Export as MP3 with good quality settings
        audio.export(
            audio_path,
            format="mp3",
            bitrate="192k",  # Good quality bitrate
            parameters=["-q:a", "2"],  # MP3 quality setting (0-9, lower is better)
        )

        logger.info(f"Successfully converted audio to MP3: {audio_path}")

    except Exception as e:
        logger.error(f"Error converting audio to MP3: {e}")
        # Clean up task if conversion fails
        task_manager.update_task(task_id, "failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to convert audio to MP3: {str(e)}",
        )
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_path):
            os.unlink(temp_path)

    # The SRT filename will match the MP3 filename (without extension)
    srt_filename = f"{task_id}_{Path(file.filename).stem}.srt"
    srt_path = os.path.join(settings.OUTPUT_DIR, srt_filename)
    output_dir = settings.OUTPUT_DIR

    # Generate a title from the filename (remove extension)
    transcription_title = Path(file.filename).stem

    # Extract audio duration from the converted MP3 file
    audio_duration = get_audio_duration(audio_path)
    if audio_duration is None:
        logger.warning(
            f"Could not extract audio duration for {audio_path}, setting to 0"
        )
        audio_duration = 0.0

    await create_transcription(
        session=session,
        transcription_data=CreateTranscriptionParams(
            user_id=current_user.user_id,
            group_id=current_user.group_id,
            task_id=task_id,
            transcription_title=transcription_title,
            filename=file.filename,
            audio_path=audio_path,
            srt_path=srt_path,
            language=language,
            status="pending",
            audio_duration=audio_duration,  # Add the extracted duration
            extra_metadata={
                "file_size": os.path.getsize(audio_path),
                "original_filename": file.filename,
                "converted_to_mp3": True,
                "original_format": file_extension,
            },
        ),
    )

    background_tasks.add_task(
        queue_audio_processing,
        task_id,
        audio_path,
        output_dir,
        language,
        settings.HUG_TOKEN,
    )

    return {
        "task_id": task_id,
        "message": "Transcription task started",
        "status_url": f"/task/{task_id}",
    }


@router.get("/v1/tasks")
async def _list_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    session: AsyncSession = Depends(get_db_session),
):
    """List transcription tasks based on user role permissions"""

    # Filter tasks based on user role
    if current_user.role == Role.SUPER_ADMIN.value:
        # Super admin can see all tasks
        tasks = [task.to_dict() for task in task_manager.tasks.values()]

    elif current_user.role == Role.ADMIN.value:
        # Admin can see all tasks except super_admin's tasks
        super_admin_group_id = await get_super_admin_group_id(session)

        tasks = [
            task.to_dict()
            for task in task_manager.tasks.values()
            if task.group_id != super_admin_group_id
        ]

    else:  # Regular user
        # Users can only see tasks from their own group
        tasks = [
            task.to_dict()
            for task in task_manager.tasks.values()
            if task.group_id == current_user.group_id
        ]

    # Filter by status for all roles
    tasks = [
        task for task in tasks if task["status"] in ["processing", "pending", "queued"]
    ]

    return {"count": len(tasks), "tasks": tasks}


@router.get(
    "/v1/transcriptions", response_model=PaginatedDataResponse[GetTranscriptionResponse]
)
async def _get_transcriptions(
    current_user: Annotated[User, Depends(get_current_user)],
    query_params: Annotated[GetTranscriptionsParams, Query()],
    session: AsyncSession = Depends(get_db_session),
):
    try:
        return await get_transcriptions(
            user=current_user,
            session=session,
            name=query_params.name,
            page=query_params.page,
            page_size=query_params.page_size,
        )
    except HTTPException as exc:
        logger.error("get_transcriptions error")
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.error("get_transcriptions error")
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get(
    "/v1/transcription/{transcription_id}",
    response_model=DataResponse[GetTranscriptionByTranscriptionIdResponse],
)
async def _get_transcription_detail(
    transcription_id: int, session: AsyncSession = Depends(get_db_session)
):
    try:
        return await get_transcription_by_transcription_id(
            session=session, transcription_id=transcription_id
        )

    except HTTPException as exc:
        logger.error("get_transcription_endpoint error")
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.error("get_transcription_endpoint error")
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.delete("/v1/transcription/{transcription_id}")
async def _delete_transcription_endpoint(
    transcription_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    transcription_response = await get_transcription_by_transcription_id(
        session=session, transcription_id=transcription_id
    )
    if not transcription_response or not transcription_response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transcription not found"
        )

    # We need to get the full transcription record to access file paths
    # The get_transcription_by_transcription_id only returns selected fields
    result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
    transcription = result.scalar_one_or_none()

    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")

    files_deleted = []
    for file_path in [
        transcription.audio_path,
        transcription.srt_path,
    ]:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                files_deleted.append(file_path)
            except Exception as e:
                # Log error but continue
                print(f"Error deleting file {file_path}: {e}")

    # Delete from database
    success = await delete_transcription_by_id(session, transcription_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete transcription")

    response = {
        "message": "Transcription deleted successfully",
        "transcription_id": transcription_id,
    }

    response["files_deleted"] = files_deleted
    return response


@router.get("/v1/transcription/{transcription_id}/download")
async def _download_transcription_files(
    transcription_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Download transcription audio and SRT files as a zip archive

    Returns a zip file containing:
    - The original audio file
    - The SRT subtitle file
    """
    # Get the transcription record
    result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
    transcription = result.scalar_one_or_none()

    if not transcription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transcription not found"
        )

    # Check if files exist
    if not transcription.audio_path or not os.path.exists(transcription.audio_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found"
        )

    if not transcription.srt_path or not os.path.exists(transcription.srt_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="SRT file not found"
        )

    # Create a temporary zip file
    temp_dir = tempfile.mkdtemp()
    zip_filename = f"transcription_{transcription_id}_download.zip"
    zip_path = os.path.join(temp_dir, zip_filename)

    try:
        # Create zip file
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Add audio file with original filename
            audio_filename = Path(transcription.audio_path).name
            # Remove task_id prefix if present
            if (
                "_" in audio_filename
                and audio_filename.split("_")[0] == transcription.task_id
            ):
                audio_filename = "_".join(audio_filename.split("_")[1:])
            zipf.write(transcription.audio_path, arcname=audio_filename)

            # Add SRT file
            srt_filename = f"{transcription.transcription_title or 'subtitles'}.txt"
            zipf.write(transcription.srt_path, arcname=srt_filename)

            # Add summary file if available
            if transcription.summary:
                summary_filename = (
                    f"{transcription.transcription_title or 'summary'}_summary.txt"
                )
                # Create temporary summary file
                summary_path = os.path.join(temp_dir, summary_filename)
                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(transcription.summary)
                zipf.write(summary_path, arcname=summary_filename)
                # Clean up temporary summary file
                os.remove(summary_path)

        # Return the zip file
        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=zip_filename,
            headers={"Content-Disposition": f"attachment; filename={zip_filename}"},
        )

    except Exception as e:
        # Clean up on error
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)

        logger.error(
            f"Error creating zip file for transcription {transcription_id}: {e}"
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create download archive" + str(e),
        )


@router.get("/v1/transcription/{transcription_id}/audio")
async def _stream_audio(
    transcription_id: int,
    range: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Stream audio file with support for range requests.
    This endpoint is used by audio players and waveform visualizers.

    Supports:
    - Range requests for seeking
    - Proper content-type detection
    - Caching headers
    """
    # Get the transcription record
    result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
    transcription = result.scalar_one_or_none()

    if not transcription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transcription not found"
        )

    # Check if audio file exists
    audio_path = transcription.audio_path
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found"
        )

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
    if not range:
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
    range_match = re.search(r"bytes=(\d+)-(\d*)", range)
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


@router.put(
    "/v1/transcription/{transcription_id}",
    response_model=DetailResponse,
)
async def _update_transcription(
    transcription_id: Annotated[int, Path()],
    transcription_data: Annotated[UpdateTranscriptionParams, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await update_transcription_api(
            session=session,
            transcription_id=transcription_id,
            transcription_data=transcription_data,
        )

        return DetailResponse(detail="User password reset successfully")

    except HTTPException as exc:
        logger.error("Update group error")
        logger.exception(exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except Exception as exc:
        logger.error("Update group error")
        logger.exception(exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
