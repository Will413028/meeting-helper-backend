"""Background processor for transcription tasks using proper async handling"""

import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
import subprocess

from src.whisperx_diarize import whisperx_diarize_with_progress
from src.task_manager import task_manager, TaskStatus
from src.database import AsyncSessionLocal
from src.transcription.service import update_transcription
from src.logger import logger

# Global dictionary to track running processes
running_processes: Dict[str, subprocess.Popen] = {}

# Global queue processor task
_queue_processor_task: Optional[asyncio.Task] = None


async def start_queue_processor():
    """Start the global queue processor if not already running"""
    global _queue_processor_task
    if _queue_processor_task is None or _queue_processor_task.done():
        _queue_processor_task = asyncio.create_task(_process_queue())
        logger.info("Started queue processor task")


async def _process_queue():
    """Continuously process tasks from the queue"""
    while True:
        try:
            # Check if we can process a task
            if await task_manager.is_processing_available():
                # Get next task from queue
                task_id = await task_manager.get_next_task()
                if task_id:
                    logger.info(f"Processing next task from queue: {task_id}")
                    # Get task details from database
                    async with AsyncSessionLocal() as session:
                        from sqlalchemy import select
                        from src.models import Transcription

                        result = await session.execute(
                            select(Transcription).filter_by(task_id=task_id)
                        )
                        transcription = result.scalar_one_or_none()

                        if transcription:
                            # Process the task
                            await process_audio_async(
                                task_id=task_id,
                                audio_path=transcription.audio_path,
                                output_dir=os.path.dirname(transcription.srt_path),
                                language=transcription.language,
                                hug_token=os.getenv("HUG_TOKEN", ""),
                            )
                        else:
                            logger.error(f"Task {task_id} not found in database")
                            await task_manager.fail_task(
                                task_id, "Task not found in database"
                            )

            # Wait a bit before checking again
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error in queue processor: {e}")
            await asyncio.sleep(5)  # Wait longer on error


async def queue_audio_processing(
    task_id: str,
    audio_path: str,
    output_dir: str,
    language: str,
    hug_token: str,
):
    """Add audio processing task to queue"""
    # Add to queue
    await task_manager.add_to_queue(task_id)

    # Update database status
    async with AsyncSessionLocal() as session:
        await update_transcription(session, task_id=task_id, status="queued")

    # Ensure queue processor is running
    await start_queue_processor()

    logger.info(f"Task {task_id} added to queue")


async def process_audio_async(
    task_id: str,
    audio_path: str,
    output_dir: str,
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

        # Check if task was cancelled before starting
        task = task_manager.get_task(task_id)
        if task and task.status == TaskStatus.CANCELLED:
            logger.info(f"Task {task_id} was cancelled before processing started")
            await _cleanup_cancelled_task(task_id, audio_path)
            return

        # Run WhisperX with cancellation support
        await _run_whisperx_with_cancellation(
            task_id=task_id,
            audio_path=audio_path,
            output_dir=output_dir,
            model="large-v3",
            align_model="WAV2VEC2_ASR_LARGE_LV60K_960H",
            language=language,
            chunk_size=6,
            hug_token=hug_token,
            initial_prompt="",
            progress_callback=sync_progress_callback,
        )

        # Check if task was cancelled during processing
        task = task_manager.get_task(task_id)
        if task and task.status == TaskStatus.CANCELLED:
            logger.info(f"Task {task_id} was cancelled during processing")
            await _cleanup_cancelled_task(task_id, audio_path)
            return

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
        await task_manager.complete_task(task_id, result)

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
        await task_manager.fail_task(task_id, str(e))

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


async def _run_whisperx_with_cancellation(
    task_id: str,
    audio_path: str,
    output_dir: str,
    model: str,
    align_model: str,
    language: str,
    chunk_size: int,
    hug_token: str,
    initial_prompt: str,
    progress_callback,
):
    """Run WhisperX in a way that can be cancelled"""
    # We need to modify whisperx_diarize_with_progress to return the process
    # For now, we'll create a wrapper that can check for cancellation
    loop = asyncio.get_event_loop()

    def run_with_cancellation_check():
        # Create a modified progress callback that checks for cancellation
        def cancellable_progress_callback(
            progress: int, step: str, estimated_completion
        ):
            # Check if task was cancelled
            task = task_manager.get_task(task_id)
            if task and task.status == TaskStatus.CANCELLED:
                # This will be caught by the caller
                raise Exception("Task was cancelled by user")

            # Call the original progress callback
            if progress_callback:
                progress_callback(progress, step, estimated_completion)

        # Run with the cancellable callback and task_id
        whisperx_diarize_with_progress(
            audio_path=audio_path,
            output_dir=output_dir,
            model=model,
            align_model=align_model,
            language=language,
            chunk_size=chunk_size,
            hug_token=hug_token,
            initial_prompt=initial_prompt,
            progress_callback=cancellable_progress_callback,
            task_id=task_id,  # Pass task_id for process tracking
        )

    # Run in executor to avoid blocking
    try:
        await loop.run_in_executor(None, run_with_cancellation_check)
    except Exception as e:
        if "cancelled by user" in str(e).lower():
            # This is expected for cancelled tasks
            logger.info(f"Task {task_id} execution stopped due to cancellation")
            raise
        else:
            # Re-raise other exceptions
            raise


async def _cleanup_cancelled_task(task_id: str, audio_path: str):
    """Clean up resources for a cancelled task"""
    # Update database
    async with AsyncSessionLocal() as session:
        await update_transcription(
            session,
            task_id=task_id,
            status="cancelled",
            completed_at=datetime.now(),
            current_step="Cancelled by user",
        )

    # Clean up audio file
    if os.path.exists(audio_path):
        try:
            os.remove(audio_path)
            logger.info(f"Cleaned up audio file for cancelled task {task_id}")
        except Exception as e:
            logger.error(f"Error cleaning up audio file {audio_path}: {e}")


async def cancel_transcription_task(task_id: str) -> bool:
    """Cancel a running transcription task"""
    # First, update the task status
    cancelled = await task_manager.cancel_task(task_id)

    if cancelled:
        # Try to terminate the WhisperX process if it's running
        from src.whisperx_diarize import terminate_process

        process_terminated = terminate_process(task_id)
        if process_terminated:
            logger.info(f"Terminated WhisperX process for task {task_id}")

        # Update database
        async with AsyncSessionLocal() as session:
            await update_transcription(
                session,
                task_id=task_id,
                status="cancelled",
                completed_at=datetime.now(),
                current_step="Cancelled by user",
            )

        logger.info(f"Successfully cancelled task {task_id}")
        return True

    return False
