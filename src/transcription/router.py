import os
from pathlib import Path
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
    Query,
    Body,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.transcription.file_service import get_audio_file_response
from src.auth.dependencies import get_current_user
from src.core.config import settings
from src.core.constants import Role
from src.core.database import get_db_session
from src.group.service import get_super_admin_group_id
from src.core.logger import logger
from src.models import Transcription, User
from src.core.schemas import DataResponse, DetailResponse, PaginatedDataResponse
from src.task_manager import task_manager
from src.transcription.audio_service import convert_to_mp3, create_transcription_zip
from src.transcription.background_processor import queue_audio_processing
from src.transcription.schemas import (
    CreateTranscriptionParams,
    GetTranscriptionByTranscriptionIdResponse,
    GetTranscriptionResponse,
    GetTranscriptionsParams,
    UpdateTranscriptionParams,
)
from src.transcription.service import (
    create_transcription,
    delete_transcription_service,
    get_transcription_by_transcription_id,
    get_transcriptions,
    update_transcription_api,
)
from src.transcription.audio_utils import (
    is_supported_audio_file,
    ALLOWED_AUDIO_EXTENSIONS,
)

router = APIRouter(tags=["transcription"])


@router.post("/v1/transcribe")
async def transcribe_audio_handler(
    current_user: Annotated[User, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = Form(default="zh"),
    session: AsyncSession = Depends(get_db_session),
):
    """Upload an audio file and start async transcription with progress tracking"""

    if not is_supported_audio_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not supported. Allowed types: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}",
        )

    # Create task
    task_id = task_manager.create_task(
        filename=file.filename, group_id=current_user.group_id
    )

    try:
        # Run blocking audio conversion in a separate thread
        audio_path, audio_duration = await run_in_threadpool(
            convert_to_mp3, file=file, task_id=task_id, output_dir=settings.OUTPUT_DIR
        )

    except Exception as e:
        logger.error(f"Error converting audio: {e}")
        task_manager.update_task(task_id, "failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process audio file: {str(e)}",
        )

    # The SRT filename will match the MP3 filename (without extension)
    # Note: audio_path comes from the service, effectively "{task_id}_{stem}.mp3"
    transcription_title = Path(file.filename).stem
    srt_filename = f"{task_id}_{transcription_title}.srt"
    srt_path = os.path.join(settings.OUTPUT_DIR, srt_filename)

    file_extension = Path(file.filename).suffix.lower()

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
            audio_duration=audio_duration,
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
        settings.OUTPUT_DIR,
        language,
        settings.HUG_TOKEN,
    )

    return {
        "task_id": task_id,
        "message": "Transcription task started",
        "status_url": f"/task/{task_id}",
    }


@router.get("/v1/tasks")
async def list_tasks_handler(
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
async def get_transcriptions_handler(
    current_user: Annotated[User, Depends(get_current_user)],
    query_params: Annotated[GetTranscriptionsParams, Query()],
    session: AsyncSession = Depends(get_db_session),
):
    return await get_transcriptions(
        user=current_user,
        session=session,
        name=query_params.name,
        page=query_params.page,
        page_size=query_params.page_size,
    )


@router.get(
    "/v1/transcription/{transcription_id}",
    response_model=DataResponse[GetTranscriptionByTranscriptionIdResponse],
)
async def get_transcription_detail_handler(
    transcription_id: int, session: AsyncSession = Depends(get_db_session)
):
    return await get_transcription_by_transcription_id(
        session=session, transcription_id=transcription_id
    )


@router.delete("/v1/transcription/{transcription_id}")
async def delete_transcription_endpoint_handler(
    transcription_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    result = await delete_transcription_service(session, transcription_id)

    if not result["success"]:
        error_msg = result.get("error", "Failed to delete transcription")
        if error_msg == "Transcription not found":
            raise HTTPException(status_code=404, detail="Transcription not found")
        raise HTTPException(status_code=500, detail=error_msg)

    response = {
        "message": "Transcription deleted successfully",
        "transcription_id": transcription_id,
        "files_deleted": result.get("files_deleted", []),
    }
    return response


@router.get("/v1/transcription/{transcription_id}/download")
async def download_transcription_files_handler(
    transcription_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Download transcription audio and SRT files as a zip archive
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

    try:
        # Use service to create zip without blocking
        zip_path = await run_in_threadpool(
            create_transcription_zip,
            transcription_id=transcription_id,
            task_id=transcription.task_id,
            audio_path=transcription.audio_path,
            srt_path=transcription.srt_path,
            transcription_title=transcription.transcription_title,
            summary=transcription.summary,
        )

        zip_filename = Path(zip_path).name

        # Return the zip file
        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=zip_filename,
            headers={"Content-Disposition": f"attachment; filename={zip_filename}"},
        )

    except Exception as e:
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
async def stream_audio_handler(
    transcription_id: int,
    range: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Stream audio file with support for range requests.
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
    # Determine content type and handle partial content responses are delegated to the service

    return get_audio_file_response(audio_path, range)


@router.put(
    "/v1/transcription/{transcription_id}",
    response_model=DetailResponse,
)
async def update_transcription_handler(
    transcription_id: Annotated[int, Path()],
    transcription_data: Annotated[UpdateTranscriptionParams, Body()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    await update_transcription_api(
        session=session,
        transcription_id=transcription_id,
        transcription_data=transcription_data,
    )
    return DetailResponse(detail="User password reset successfully")
