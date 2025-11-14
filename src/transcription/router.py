import os
import re
import shutil
import zipfile
import tempfile
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta
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
    cleanup_old_transcriptions,
    get_transcriptions,
    update_transcription_api,
    update_transcription,
)
from src.transcription.ollama_service import generate_summary, check_ollama_availability
from src.transcription.srt_utils import extract_text_from_srt
from src.transcription.schemas import (
    CreateTranscriptionParams,
    GetTranscriptionsParams,
    GetTranscriptionByTranscriptionIdResponse,
    GetTranscriptionResponse,
    UpdateTranscriptionParams,
)
from src.transcription.background_processor import (
    cancel_transcription_task,
)
from src.transcription.audio_utils import get_audio_duration
from src.schemas import PaginatedDataResponse, DataResponse, DetailResponse
from src.transcription.background_processor import queue_audio_processing
from src.database import AsyncSessionLocal

router = APIRouter(tags=["transcription"])


@router.post("/v1/transcribe")
async def _transcribe_audio(
    current_user: Annotated[User, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form(default="zh"),
    session: AsyncSession = Depends(get_db_session),
):
    logger.info(f"language: {language}")
    """
    Upload an audio file and start async transcription with progress tracking

    Returns task_id to track progress
    """
    # Validate file extension
    allowed_extensions = [".mp3", ".wav", ".mp4", ".m4a", ".flac", ".ogg", ".webm"]
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}",
        )

    # Create task
    task_id = task_manager.create_task(file.filename)

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


@router.get("/v1/task/{task_id}")
async def _get_task_status(task_id: str):
    """Get the status and progress of a transcription task"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    return task.to_dict()


@router.get("/v1/tasks")
async def _list_tasks():
    """List all transcription tasks"""
    tasks = [task.to_dict() for task in task_manager.tasks.values()]

    tasks = [task for task in tasks if task["status"] in ["processing", "pending"]]

    return {"count": len(tasks), "tasks": tasks}


@router.get("/v1/queue/status")
async def _get_queue_status():
    """Get the current queue status"""
    queue_status = task_manager.get_queue_status()

    # Get details of current processing task
    current_task = None
    if queue_status["current_processing"]:
        task = task_manager.get_task(queue_status["current_processing"])
        if task:
            current_task = {
                "task_id": task.task_id,
                "filename": task.filename,
                "progress": task.progress,
                "current_step": task.current_step,
            }

    # Get details of queued tasks
    queued_tasks = []
    for task_id in queue_status["queued_tasks"]:
        task = task_manager.get_task(task_id)
        if task:
            queued_tasks.append(
                {
                    "task_id": task.task_id,
                    "filename": task.filename,
                    "queue_position": task.queue_position,
                }
            )

    return {
        "current_processing": current_task,
        "queue_length": queue_status["queue_length"],
        "queued_tasks": queued_tasks,
    }


@router.post("/v1/task/{task_id}/cancel")
async def _cancel_task(task_id: str):
    """Cancel a running transcription task"""
    # Check if task exists
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    # Check if task can be cancelled
    if task.status.value not in ["pending", "processing"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task cannot be cancelled. Current status: {task.status.value}",
        )

    # Cancel the task
    success = await cancel_transcription_task(task_id)

    if success:
        return {
            "task_id": task_id,
            "message": "Task cancelled successfully",
            "status": "cancelled",
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel task",
        )


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


@router.post("/v1/transcriptions/cleanup")
async def _cleanup_old_transcriptions_endpoint(
    days: int = 30,
    delete_files: bool = False,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Clean up transcriptions older than specified days

    Args:
        days: Delete transcriptions older than this many days (default: 30)
        delete_files: Whether to also delete associated files
    """
    if days < 1:
        raise HTTPException(status_code=400, detail="Days must be at least 1")

    # Get old transcriptions before deletion if we need to delete files
    files_deleted = []
    if delete_files:
        # Query database directly to get full transcription records with file paths
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        result = await session.execute(
            select(Transcription).where(Transcription.created_at < cutoff_date)
        )
        old_transcriptions = result.scalars().all()

        for trans in old_transcriptions:
            # Delete associated files
            for file_path in [trans.audio_path, trans.srt_path]:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        files_deleted.append(file_path)
                    except Exception as e:
                        logger.error(f"Error deleting file {file_path}: {e}")

    # Clean up database records
    deleted_count = await cleanup_old_transcriptions(session, days=days)

    response = {
        "message": f"Cleaned up {deleted_count} transcriptions older than {days} days",
        "deleted_count": deleted_count,
    }

    if delete_files:
        response["files_deleted"] = len(files_deleted)
        response["file_paths"] = files_deleted

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


@router.get("/v1/transcription/{transcription_id}/audio/info")
async def _get_audio_info(
    transcription_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get audio file metadata.
    Useful for frontend to display information before loading the audio.
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

    audio_path = transcription.audio_path
    if not audio_path or not os.path.exists(audio_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found"
        )

    file_size = os.path.getsize(audio_path)
    file_extension = os.path.splitext(audio_path)[1][1:]  # Remove the dot

    return {
        "transcription_id": transcription_id,
        "filename": transcription.filename,
        "title": transcription.transcription_title,
        "size_bytes": file_size,
        "size_mb": round(file_size / (1024 * 1024), 2),
        "duration": transcription.audio_duration,
        "format": file_extension,
        "language": transcription.language,
        "created_at": transcription.created_at.isoformat()
        if transcription.created_at
        else None,
        "has_srt": bool(
            transcription.srt_path and os.path.exists(transcription.srt_path)
        ),
    }


@router.get("/v1/transcription/{transcription_id}/srt")
async def _get_srt_content(
    transcription_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get SRT subtitle content as plain text.
    Used by frontend to display synchronized subtitles with audio playback.
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

    srt_path = transcription.srt_path
    if not srt_path or not os.path.exists(srt_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="SRT file not found"
        )

    # Read SRT content
    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        logger.error(
            f"Error reading SRT file for transcription {transcription_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to read SRT file",
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


@router.post("/v1/transcription/{transcription_id}/generate-summary")
async def _generate_summary_for_transcription(
    transcription_id: int,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
):
    """Generate or regenerate summary for an existing transcription"""

    # Get transcription details
    result = await session.execute(
        select(Transcription).filter_by(transcription_id=transcription_id)
    )
    transcription = result.scalar_one_or_none()

    if not transcription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcription not found",
        )

    # Check if Ollama is available
    if not await check_ollama_availability():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama service is not available",
        )

    # Extract text from SRT if not already available
    transcription_text = transcription.transcription_text
    if not transcription_text and transcription.srt_path:
        if os.path.exists(transcription.srt_path):
            # Extract text with speaker information preserved
            transcription_text = extract_text_from_srt(
                transcription.srt_path,
                convert_to_traditional=True,
                preserve_speakers=True,
            )
            if transcription_text:
                # Save the extracted text
                await update_transcription(
                    session,
                    task_id=transcription.task_id,
                    transcription_text=transcription_text,
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SRT file not found",
            )

    if not transcription_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No transcription text available",
        )

    # Generate summary in background
    async def generate_and_save_summary():
        try:
            summary = await generate_summary(transcription_text)
            if summary:
                async with AsyncSessionLocal() as session:
                    await update_transcription(
                        session, task_id=transcription.task_id, summary=summary
                    )
                logger.info(
                    f"Successfully generated summary for transcription {transcription_id}"
                )
            else:
                logger.error(
                    f"Failed to generate summary for transcription {transcription_id}"
                )
        except Exception as e:
            logger.error(
                f"Error generating summary for transcription {transcription_id}: {e}"
            )

    background_tasks.add_task(generate_and_save_summary)

    return {
        "message": "Summary generation started",
        "transcription_id": transcription_id,
    }
