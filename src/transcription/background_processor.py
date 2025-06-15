"""Background processor for transcription tasks using proper async handling"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from src.whisperx_diarize_async import whisperx_diarize_with_progress
from src.task_manager import task_manager
from src.database import AsyncSessionLocal
from src.transcription.service import update_transcription
from src.logger import logger


async def process_audio_async(
    task_id: str,
    audio_path: str,
    output_dir: str,
    model: str,
    language: str,
    hug_token: str,
):
    """Async function to process audio with progress tracking"""
    try:
        # Start the task
        task_manager.start_task(task_id)

        # Update database status
        async with AsyncSessionLocal() as session:
            await update_transcription(
                session, task_id=task_id, status="processing", started_at=datetime.now()
            )

        # Create a progress callback that updates both task manager and database
        async def async_progress_callback(
            progress: int, step: str, estimated_completion: Optional[datetime]
        ):
            # Update task manager (in-memory)
            task_manager.update_task_progress(
                task_id, progress, step, estimated_completion
            )

            # Update database
            async with AsyncSessionLocal() as session:
                await update_transcription(
                    session,
                    task_id=task_id,
                    progress=progress,
                    current_step=step,
                    estimated_completion_time=estimated_completion,
                )

        # We need to wrap the sync whisperx function to work with async
        # For now, we'll use a simpler approach
        def sync_progress_callback(
            progress: int, step: str, estimated_completion: Optional[datetime]
        ):
            # Store the update info to be processed later
            task_manager.update_task_progress(
                task_id, progress, step, estimated_completion
            )

        # Run WhisperX (this is still sync, but we won't try to do async DB updates from it)
        whisperx_diarize_with_progress(
            audio_path=audio_path,
            output_dir=output_dir,
            model=model,
            align_model="WAV2VEC2_ASR_LARGE_LV60K_960H",
            language=language,
            chunk_size=6,
            hug_token=hug_token,
            initial_prompt="",
            progress_callback=sync_progress_callback,
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

        # Update database with completion
        async with AsyncSessionLocal() as session:
            await update_transcription(
                session,
                task_id=task_id,
                status="completed",
                completed_at=datetime.now(),
                srt_path=srt_file_path,
                result=result,
                progress=100,
            )

        logger.info(f"Successfully completed transcription task {task_id}")

    except Exception as e:
        logger.error(f"Error processing audio for task {task_id}: {e}")

        # Update task manager
        task_manager.fail_task(task_id, str(e))

        # Update database
        try:
            async with AsyncSessionLocal() as session:
                await update_transcription(
                    session,
                    task_id=task_id,
                    status="failed",
                    completed_at=datetime.now(),
                )
        except Exception as db_error:
            logger.error(
                f"Error updating database for failed task {task_id}: {db_error}"
            )

        # Clean up audio file on error
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception as cleanup_error:
                logger.error(
                    f"Error cleaning up audio file {audio_path}: {cleanup_error}"
                )
