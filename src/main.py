import os
import shutil
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from src.whisperx_diarize import whisperx_diarize
from src.whisperx_diarize_async import whisperx_diarize_with_progress
from src.task_manager import task_manager
from src.config import settings
from src.database import db

app = FastAPI()

# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)


@app.on_event("startup")
async def startup_event():
    """Create output directory if it doesn't exist"""
    os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
    # Database will be initialized automatically when imported


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/transcribe/")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = "large-v3",
    language: str = "zh",
):
    """
    Upload an audio file and get SRT transcription using WhisperX

    Args:
        file: Audio file (mp3, wav, mp4, etc.)
        model: WhisperX model to use (default: large-v3)
        language: Language code (default: zh for Chinese)
        hf_token: HuggingFace token for speaker diarization

    Returns:
        SRT file with transcription
    """
    # Validate file extension
    allowed_extensions = [".mp3", ".wav", ".mp4", ".m4a", ".flac", ".ogg", ".webm"]
    file_extension = Path(file.filename).suffix.lower()
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed types: {', '.join(allowed_extensions)}",
        )

    # Save uploaded file in output directory
    audio_filename = f"{Path(file.filename).stem}{file_extension}"
    audio_path = os.path.join(settings.OUTPUT_DIR, audio_filename)
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    output_dir = settings.OUTPUT_DIR

    try:
        whisperx_diarize(
            audio_path=audio_path,
            output_dir=output_dir,
            model=model,
            align_model="WAV2VEC2_ASR_LARGE_LV60K_960H",
            language=language,
            chunk_size=6,
            hug_token=settings.HUG_TOKEN,
            initial_prompt="",
        )

        # Check if SRT file was generated
        # WhisperX generates output file with the same base name as input
        srt_filename = f"{Path(file.filename).stem}.srt"
        srt_file_path = os.path.join(output_dir, srt_filename)

        if not os.path.exists(srt_file_path):
            # Try alternative naming pattern
            alt_srt_path = os.path.join(output_dir, f"{Path(audio_filename).stem}.srt")
            if os.path.exists(alt_srt_path):
                srt_file_path = alt_srt_path
                srt_filename = os.path.basename(alt_srt_path)
            else:
                raise HTTPException(
                    status_code=500, detail="Failed to generate SRT file"
                )

        # Save to database
        task_id = str(Path(file.filename).stem) + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        db.save_transcription(
            task_id=task_id,
            filename=file.filename,
            audio_path=audio_path,
            srt_path=srt_file_path,
            model=model,
            language=language,
            status="completed",
            extra_metadata={
                "file_size": os.path.getsize(audio_path),
                "srt_size": os.path.getsize(srt_file_path) if os.path.exists(srt_file_path) else 0
            }
        )

        # Return success response with file info
        return {
            "status": "success",
            "message": "Transcription completed successfully",
            "task_id": task_id,
            "audio_file": audio_filename,
            "srt_file": srt_filename,
            "srt_path": srt_file_path,
        }

    except Exception as e:
        # Clean up audio file on error
        if os.path.exists(audio_path):
            os.remove(audio_path)
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")


def process_audio_with_progress(
    task_id: str, audio_path: str, output_dir: str, model: str, language: str, original_filename: str
):
    """Background function to process audio with progress tracking"""
    try:
        task_manager.start_task(task_id)
        
        # Update database status
        db.update_transcription(
            task_id=task_id,
            status="processing",
            started_at=datetime.now()
        )

        def progress_callback(
            progress: int, step: str, estimated_completion: Optional[datetime]
        ):
            task_manager.update_task_progress(
                task_id, progress, step, estimated_completion
            )
            # Update database progress
            db.update_transcription(
                task_id=task_id,
                progress=progress,
                current_step=step,
                estimated_completion_time=estimated_completion
            )

        # Run WhisperX with progress tracking
        whisperx_diarize_with_progress(
            audio_path=audio_path,
            output_dir=output_dir,
            model=model,
            align_model="WAV2VEC2_ASR_LARGE_LV60K_960H",
            language=language,
            chunk_size=6,
            hug_token=settings.HUG_TOKEN,
            initial_prompt="",
            progress_callback=progress_callback,
        )

        # Check if SRT file was generated
        srt_filename = f"{Path(audio_path).stem}.srt"
        srt_file_path = os.path.join(output_dir, srt_filename)

        if not os.path.exists(srt_file_path):
            raise Exception("Failed to generate SRT file")

        # Complete the task
        result = {
            "audio_file": os.path.basename(audio_path),
            "srt_file": srt_filename,
            "srt_path": srt_file_path,
        }
        task_manager.complete_task(task_id, result)
        
        # Update database
        db.update_transcription(
            task_id=task_id,
            status="completed",
            completed_at=datetime.now(),
            srt_path=srt_file_path,
            result=result,
            progress=100
        )

    except Exception as e:
        task_manager.fail_task(task_id, str(e))
        
        # Update database
        db.update_transcription(
            task_id=task_id,
            status="failed",
            completed_at=datetime.now(),
            error_message=str(e)
        )
        
        # Clean up audio file on error
        if os.path.exists(audio_path):
            os.remove(audio_path)


@app.post("/transcribe/async")
async def transcribe_audio_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: str = "large-v3",
    language: str = "zh",
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
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    output_dir = settings.OUTPUT_DIR
    
    # Save to database
    db.save_transcription(
        task_id=task_id,
        filename=file.filename,
        audio_path=audio_path,
        model=model,
        language=language,
        status="pending",
        extra_metadata={
            "file_size": os.path.getsize(audio_path),
            "original_filename": file.filename
        }
    )

    # Start background processing
    background_tasks.add_task(
        process_audio_with_progress, task_id, audio_path, output_dir, model, language, file.filename
    )

    return {
        "task_id": task_id,
        "message": "Transcription task started",
        "status_url": f"/task/{task_id}",
    }


@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Get the status and progress of a transcription task"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task.to_dict()


@app.get("/tasks")
async def list_tasks():
    """List all transcription tasks"""
    tasks = [task.to_dict() for task in task_manager.tasks.values()]
    return {"count": len(tasks), "tasks": tasks}


@app.get("/disk-space")
async def get_disk_space():
    """Get remaining disk space in GB"""
    try:
        # Get disk usage statistics for the root filesystem
        disk_usage = shutil.disk_usage("/")
        
        # Convert bytes to GB (1 GB = 1024^3 bytes)
        total_gb = disk_usage.total / (1024 ** 3)
        used_gb = disk_usage.used / (1024 ** 3)
        free_gb = disk_usage.free / (1024 ** 3)
        
        # Calculate percentage used
        percent_used = (disk_usage.used / disk_usage.total) * 100
        
        return {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "percent_used": round(percent_used, 2),
            "mount_point": "/"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting disk space: {str(e)}")


@app.get("/transcriptions")
async def list_transcriptions(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None
):
    """
    List all transcriptions from database with pagination
    
    Args:
        limit: Maximum number of records to return (default: 100)
        offset: Number of records to skip (default: 0)
        status: Filter by status (pending, processing, completed, failed)
    
    Returns:
        List of transcription records
    """
    transcriptions = db.list_transcriptions(limit=limit, offset=offset, status=status)
    total = db.count_transcriptions(status=status)
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "transcriptions": transcriptions
    }


@app.get("/transcription/{task_id}")
async def get_transcription(task_id: str):
    """Get a specific transcription record by task_id"""
    transcription = db.get_transcription(task_id)
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")
    
    return transcription


@app.get("/transcription/by-filename/{filename}")
async def get_transcription_by_filename(filename: str):
    """Get the most recent transcription for a specific filename"""
    transcription = db.get_transcription_by_filename(filename)
    if not transcription:
        raise HTTPException(status_code=404, detail="No transcription found for this filename")
    
    return transcription


@app.delete("/transcription/{task_id}")
async def delete_transcription(task_id: str, delete_files: bool = False):
    """
    Delete a transcription record
    
    Args:
        task_id: The task ID to delete
        delete_files: Whether to also delete associated audio and SRT files
    """
    # Get transcription details before deletion
    transcription = db.get_transcription(task_id)
    if not transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")
    
    # Delete files if requested
    if delete_files:
        files_deleted = []
        for file_path in [transcription.get('audio_path'), transcription.get('srt_path')]:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    files_deleted.append(file_path)
                except Exception as e:
                    # Log error but continue
                    print(f"Error deleting file {file_path}: {e}")
    
    # Delete from database
    success = db.delete_transcription(task_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete transcription")
    
    response = {
        "message": "Transcription deleted successfully",
        "task_id": task_id
    }
    
    if delete_files:
        response["files_deleted"] = files_deleted
    
    return response


@app.post("/transcriptions/cleanup")
async def cleanup_old_transcriptions(days: int = 30, delete_files: bool = False):
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
        old_transcriptions = db.list_transcriptions(limit=1000)  # Get a large batch
        cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
        
        for trans in old_transcriptions:
            # Check if transcription is old enough
            created_at = datetime.fromisoformat(trans['created_at']).timestamp()
            if created_at < cutoff_date:
                # Delete associated files
                for file_path in [trans.get('audio_path'), trans.get('srt_path')]:
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            files_deleted.append(file_path)
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")
    
    # Clean up database records
    deleted_count = db.cleanup_old_transcriptions(days=days)
    
    response = {
        "message": f"Cleaned up {deleted_count} transcriptions older than {days} days",
        "deleted_count": deleted_count
    }
    
    if delete_files:
        response["files_deleted"] = len(files_deleted)
        response["file_paths"] = files_deleted
    
    return response


@app.get("/transcriptions/stats")
async def get_transcription_stats():
    """Get statistics about transcriptions"""
    total = db.count_transcriptions()
    pending = db.count_transcriptions(status="pending")
    processing = db.count_transcriptions(status="processing")
    completed = db.count_transcriptions(status="completed")
    failed = db.count_transcriptions(status="failed")
    
    disk_stats = db.get_disk_usage_stats()
    
    return {
        "total_transcriptions": total,
        "by_status": {
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed
        },
        "disk_usage": disk_stats
    }
