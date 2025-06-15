import os
import shutil
from pathlib import Path
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
    BackgroundTasks,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db_session
from src.logger import logger
from src.models import Transcription
from src.task_manager import task_manager
from src.config import settings
from src.transcription.service import (
    create_transcription,
    get_transcription_by_transcription_id,
    list_transcriptions,
    delete_transcription_by_id,
    cleanup_old_transcriptions,
)
from src.transcription.schemas import CreateTranscriptionParams
from src.transcription.background_processor import process_audio_async

router = APIRouter(tags=["transcription"])


@router.post("/v1/transcribe/async")
async def transcribe_audio_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = "zh",
    session: AsyncSession = Depends(get_db_session),
):
    """
    Upload an audio file and start async transcription with progress tracking

    Returns task_id to track progress
    """
    # Validate file extension
    allowed_extensions = [".mp3", ".wav", ".mp4", ".m4a", ".flac", ".ogg", ".webm"]
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}",
        )

    # Create task
    task_id = task_manager.create_task(file.filename)

    # Save uploaded file
    audio_filename = f"{task_id}_{Path(file.filename).stem}{file_extension}"
    audio_path = os.path.join(settings.OUTPUT_DIR, audio_filename)
    srt_path = os.path.join(settings.OUTPUT_DIR, f"{task_id}.srt")
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    output_dir = settings.OUTPUT_DIR

    # Generate a title from the filename (remove extension)
    transcription_title = Path(file.filename).stem

    await create_transcription(
        session=session,
        transcription_data=CreateTranscriptionParams(
            task_id=task_id,
            transcription_title=transcription_title,
            filename=file.filename,
            audio_path=audio_path,
            srt_path=srt_path,
            language=language,
            status="pending",
            extra_metadata={
                "file_size": os.path.getsize(audio_path),
                "original_filename": file.filename,
            },
        ),
    )

    # Start background processing with async task
    background_tasks.add_task(
        process_audio_async,
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
async def get_task_status(task_id: str):
    """Get the status and progress of a transcription task"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task.to_dict()


@router.get("/v1/tasks")
async def list_tasks():
    """List all transcription tasks"""
    tasks = [task.to_dict() for task in task_manager.tasks.values()]
    return {"count": len(tasks), "tasks": tasks}


# @router.get("/v1/transcriptions")
# async def _list_transcriptions(
#     limit: int = 100,
#     offset: int = 0,
#     status: Optional[str] = None,
#     session: AsyncSession = Depends(get_db_session),
# ):
#     transcriptions = await list_transcriptions(
#         session, limit=limit, offset=offset, status=status
#     )

#     return {
#         "total": total,
#         "limit": limit,
#         "offset": offset,
#         "transcriptions": transcriptions,
#     }


@router.get("/v1/transcription/{transcription_id}")
async def _get_transcription_endpoint(
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
async def delete_transcription_endpoint(
    transcription_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    transcription_response = await get_transcription_by_transcription_id(
        session=session, transcription_id=transcription_id
    )
    if not transcription_response or not transcription_response.data:
        raise HTTPException(status_code=404, detail="Transcription not found")

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
async def cleanup_old_transcriptions_endpoint(
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
        old_transcriptions = await list_transcriptions(
            session, limit=1000
        )  # Get a large batch
        cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)

        for trans in old_transcriptions:
            # Check if transcription is old enough
            created_at = datetime.fromisoformat(trans["created_at"]).timestamp()
            if created_at < cutoff_date:
                # Delete associated files
                for file_path in [trans.get("audio_path"), trans.get("srt_path")]:
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            files_deleted.append(file_path)
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")

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
