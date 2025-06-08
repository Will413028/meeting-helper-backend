import os
import shutil
from pathlib import Path
from typing import Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from src.whisperx_diarize import whisperx_diarize
from src.whisperx_diarize_async import whisperx_diarize_with_progress
from src.task_manager import task_manager

app = FastAPI()

# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=4)


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

    # Save uploaded file in current directory
    audio_filename = f"{Path(file.filename).stem}{file_extension}"
    audio_path = os.path.join(os.getcwd(), audio_filename)
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    output_dir = os.getcwd()

    try:
        whisperx_diarize(
            audio_path=audio_path,
            output_dir=output_dir,
            model=model,
            align_model="WAV2VEC2_ASR_LARGE_LV60K_960H",
            language=language,
            chunk_size=6,
            hug_token="REDACTED",
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

        # Return success response with file info
        return {
            "status": "success",
            "message": "Transcription completed successfully",
            "audio_file": audio_filename,
            "srt_file": srt_filename,
            "srt_path": srt_file_path,
        }

    except Exception as e:
        # Clean up audio file on error
        if os.path.exists(audio_path):
            os.remove(audio_path)
        raise HTTPException(status_code=500, detail=f"Error processing audio: {str(e)}")


def process_audio_with_progress(task_id: str, audio_path: str, output_dir: str, model: str, language: str):
    """Background function to process audio with progress tracking"""
    try:
        task_manager.start_task(task_id)
        
        def progress_callback(progress: int, step: str, estimated_completion: Optional[datetime]):
            task_manager.update_task_progress(task_id, progress, step, estimated_completion)
        
        # Run WhisperX with progress tracking
        whisperx_diarize_with_progress(
            audio_path=audio_path,
            output_dir=output_dir,
            model=model,
            align_model="WAV2VEC2_ASR_LARGE_LV60K_960H",
            language=language,
            chunk_size=6,
            hug_token="REDACTED",
            initial_prompt="",
            progress_callback=progress_callback
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
            "srt_path": srt_file_path
        }
        task_manager.complete_task(task_id, result)
        
    except Exception as e:
        task_manager.fail_task(task_id, str(e))
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
    audio_path = os.path.join(os.getcwd(), audio_filename)
    with open(audio_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    output_dir = os.getcwd()
    
    # Start background processing
    background_tasks.add_task(
        process_audio_with_progress,
        task_id,
        audio_path,
        output_dir,
        model,
        language
    )
    
    return {
        "task_id": task_id,
        "message": "Transcription task started",
        "status_url": f"/task/{task_id}"
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
    return {
        "count": len(tasks),
        "tasks": tasks
    }
