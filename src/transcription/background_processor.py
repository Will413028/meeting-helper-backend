import os
import asyncio
from sqlalchemy import select
from src.models import Transcription
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple
import subprocess
from src.segment.service import (
    initialize_segments_from_srt,
)
from src.transcription.whisperx_diarize import whisperx_diarize_with_progress
from src.task_manager import task_manager, TaskStatus, TranscriptionTask
from src.core.database import AsyncSessionLocal
from src.transcription.service import update_transcription
from src.transcription.ollama_service import (
    generate_summary,
    check_ollama_availability,
    generate_tags,
)
from src.transcription.srt_utils import (
    extract_text_from_srt,
    convert_srt_file_to_traditional,
    convert_srt_to_simple_format,
)
from src.core.logger import logger

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
                        result = await session.execute(
                            select(Transcription).filter_by(task_id=task_id)
                        )
                        transcription = result.scalar_one_or_none()

                        if transcription:
                            # Process the task
                            await process_audio(
                                task_id=task_id,
                                audio_path=transcription.audio_path,
                                output_dir=os.path.dirname(transcription.srt_path),
                                language=transcription.language,
                                hug_token=os.getenv("HUG_TOKEN", ""),
                                model=transcription.model,
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


async def _initialize_task(task_id: str) -> None:
    """Initialize task status in task manager and database."""
    task_manager.start_task(task_id)
    async with AsyncSessionLocal() as session:
        await update_transcription(
            session, task_id=task_id, status="processing", started_at=datetime.now()
        )


async def _generate_metadata(
    task_id: str, transcription_text: str, language: str, model: str
) -> Tuple[Optional[str], Optional[list]]:
    """Generate summary and tags if Ollama is available."""
    summary = None
    tags = None

    if not transcription_text:
        return None, None

    try:
        # Check if Ollama is available
        if await check_ollama_availability():
            # Generate summary
            logger.info(f"Generating summary for task {task_id}")
            summary, error_msg = await generate_summary(transcription_text, language, model)
            if summary:
                logger.info(f"Successfully generated summary for task {task_id}")
            else:
                logger.warning(
                    f"Failed to generate summary for task {task_id}: {error_msg}"
                )

            # Generate tags
            logger.info(f"Generating tags for task {task_id}")
            tags = await generate_tags(transcription_text)
            if tags:
                logger.info(
                    f"Successfully generated {len(tags)} tags for task {task_id}"
                )
            else:
                logger.warning(f"Failed to generate tags for task {task_id}")
        else:
            logger.warning(
                "Ollama is not available, skipping summary and tags generation"
            )
    except Exception as e:
        logger.error(f"Error generating summary/tags for task {task_id}: {e}")
        # Continue without summary/tags - don't fail the entire transcription

    return summary, tags


async def _complete_task(
    task_id: str,
    audio_path: str,
    srt_filename: str,
    srt_file_path: str,
    transcription_text: Optional[str],
    summary: Optional[str],
    tags: Optional[list],
) -> None:
    """Complete the task, update DB, and initialize segments."""
    # Complete the task
    result = {
        "audio_file": os.path.basename(audio_path),
        "srt_file": srt_filename,
        "srt_path": srt_file_path,
        "has_summary": summary is not None,
        "has_transcription_text": transcription_text is not None,
        "has_tags": tags is not None and len(tags) > 0,
        "tags_count": len(tags) if tags else 0,
    }
    await task_manager.complete_task(task_id, result)

    # Update database with completion
    async with AsyncSessionLocal() as session:
        update_data = {
            "status": "completed",
            "completed_at": datetime.now(),
            "srt_path": srt_file_path,
            "result": result,
            "progress": 100,
        }

        # Add transcription text, summary, and tags if available
        if transcription_text:
            update_data["transcription_text"] = transcription_text
        if summary:
            update_data["summary"] = summary
        if tags:
            update_data["tags"] = tags

        await update_transcription(session, task_id, **update_data)

        # Initialize transcript segments from the generated SRT file
        try:
            # Get the transcription record
            result = await session.execute(
                select(Transcription).filter_by(task_id=task_id)
            )
            transcription = result.scalar_one_or_none()

            if transcription and transcription.transcription_id:
                logger.info(f"Initializing transcript segments for task {task_id}")
                segments_initialized = await initialize_segments_from_srt(
                    session, transcription.transcription_id
                )
                if segments_initialized:
                    logger.info(
                        f"Successfully initialized transcript segments for task {task_id}"
                    )
                else:
                    logger.warning(
                        f"Failed to initialize transcript segments for task {task_id}"
                    )
            else:
                logger.error(f"Could not find transcription record for task {task_id}")

        except Exception as e:
            logger.error(
                f"Error initializing transcript segments for task {task_id}: {e}"
            )
            # Don't fail the entire transcription if segment initialization fails


async def _handle_process_error(
    task_id: str, audio_path: str, output_dir: str, language: str, error: Exception
) -> None:
    """Handle error during processing."""
    logger.error(f"Error processing audio for task {task_id}: {error}", exc_info=True)
    logger.error(
        f"Task {task_id} - Audio path: {audio_path}, Output dir: {output_dir}, Language: {language}"
    )
    # Update task manager
    await task_manager.fail_task(task_id, str(error))

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
        logger.error(f"Error updating database for failed task {task_id}: {db_error}")

    # Clean up audio file on error
    if os.path.exists(audio_path):
        try:
            os.remove(audio_path)
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up audio file {audio_path}: {cleanup_error}")


async def process_audio(
    task_id: str,
    audio_path: str,
    output_dir: str,
    language: str,
    hug_token: str,
    model: str,
):
    """Async function to process audio with progress tracking"""
    try:
        # Start the task
        await _initialize_task(task_id)

        # Create progress callback
        def sync_progress_callback(
            progress: int, step: str, estimated_completion: Optional[datetime]
        ):
            # Store the update info to be processed later
            task_manager.update_task_progress(
                task_id, progress, step, estimated_completion
            )
            # We also want to update DB asynchronously, but this is a sync callback
            # Creating a task here might be risky without managing it, but for logging persistence it's okay
            # asyncio.create_task(...) - skipping to avoid event loop complexity in thread

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

        _post_process_srt(task_id, srt_file_path, language)

        # Extract transcription text from SRT (already converted, preserve speaker info)
        transcription_text = extract_text_from_srt(
            srt_file_path, convert_to_traditional=False, preserve_speakers=True
        )

        # Generate summary and tags with a timeout safety net
        # This prevents the task from being stuck in processing state if Ollama hangs
        try:
            summary, tags = await asyncio.wait_for(
                _generate_metadata(task_id, transcription_text, language, model),
                timeout=360,  # 6 minutes timeout (slightly larger than Ollama timeout)
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Metadata generation for task {task_id} timed out after 6 minutes"
            )
            summary, tags = None, None
        except Exception as e:
            logger.error(
                f"Unexpected error in metadata generation for task {task_id}: {e}"
            )
            summary, tags = None, None

        # Complete the task
        await _complete_task(
            task_id=task_id,
            audio_path=audio_path,
            srt_filename=srt_filename,
            srt_file_path=srt_file_path,
            transcription_text=transcription_text,
            summary=summary,
            tags=tags,
        )

        logger.info(f"Successfully completed transcription task {task_id}")

    except Exception as e:
        await _handle_process_error(task_id, audio_path, output_dir, language, e)


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
) -> None:
    """Run WhisperX in a way that can be cancelled"""
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
    except Exception:
        # Check if it was really cancelled
        task = task_manager.get_task(task_id)
        if task and task.status == TaskStatus.CANCELLED:
            logger.info(f"Task {task_id} execution stopped due to cancellation")
        else:
            # Re-raise strictly if not cancelled
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


def _post_process_srt(task_id: str, srt_file_path: str, language: str) -> None:
    """Refined post-processing for SRT files: simplification and traditional Chinese conversion"""
    # Convert SRT to simple format (remove sequence numbers and end times)
    logger.info(f"Converting SRT to simple format for task {task_id}")
    if convert_srt_to_simple_format(srt_file_path):
        logger.info("Successfully converted SRT to simple format")
    else:
        logger.warning(
            "Failed to convert SRT to simple format, continuing with original"
        )

    # Convert SRT file: both speaker labels and text to traditional Chinese
    if language == "zh":  # Only convert for Chinese language
        logger.info(
            f"Converting SRT file (speaker labels and text) to traditional Chinese for task {task_id}"
        )
        # This will convert both speaker labels ([SPEAKER_XX]: to 講者 XX:) and text to traditional Chinese
        if convert_srt_file_to_traditional(srt_file_path, convert_speakers=True):
            logger.info(
                "Successfully converted SRT file with speaker labels to traditional Chinese"
            )
        else:
            logger.warning(
                "Failed to convert SRT file to traditional Chinese, continuing with original"
            )


async def restore_pending_tasks():
    """But restore queued tasks from database on startup"""
    try:
        logger.info("Checking for pending tasks in database...")
        async with AsyncSessionLocal() as session:
            # Find tasks that were queued or processing when server shut down
            # If they were processing, they are likely interrupted, so we should re-queue them or fail them
            # For now, let's re-queue 'queued' tasks. 'processing' tasks might need manual intervention or auto-failure
            # The user asked specifically for "queued" tasks.
            # Select tasks with status 'queued'
            result = await session.execute(
                select(Transcription).filter(
                    Transcription.status.in_([TaskStatus.QUEUED.value])
                )
            )
            tasks = result.scalars().all()

            count = 0
            for task_record in tasks:
                logger.info(f"Restoring task {task_record.task_id} from database")
                task_manager.tasks[task_record.task_id] = TranscriptionTask(
                    task_id=task_record.task_id,
                    filename=task_record.filename,
                    group_id=task_record.group_id
                    if task_record.group_id
                    else 0,  # Default to 0 if None
                )

                # Set specific fields from DB
                current_task = task_manager.get_task(task_record.task_id)
                current_task.status = TaskStatus.QUEUED
                current_task.created_at = task_record.created_at

                # Add to queue
                await task_manager.add_to_queue(task_record.task_id)
                count += 1

            # Also check for PROCESSING tasks and reset them to QUEUED
            result_processing = await session.execute(
                select(Transcription).filter(
                    Transcription.status == TaskStatus.PROCESSING.value
                )
            )
            processing_tasks = result_processing.scalars().all()
            for task_record in processing_tasks:
                logger.warning(
                    f"Task {task_record.task_id} was interrupted during processing. Re-queuing."
                )

                # Update status in DB
                task_record.status = TaskStatus.QUEUED.value
                task_record.current_step = "Interrupted, re-queued"
                session.add(task_record)

                task_manager.tasks[task_record.task_id] = TranscriptionTask(
                    task_id=task_record.task_id,
                    filename=task_record.filename,
                    group_id=task_record.group_id if task_record.group_id else 0,
                )
                current_task = task_manager.get_task(task_record.task_id)
                current_task.status = TaskStatus.QUEUED
                current_task.created_at = task_record.created_at

                # Add to queue
                await task_manager.add_to_queue(task_record.task_id)
                count += 1

            await session.commit()

            if count > 0:
                logger.info(f"Restored {count} pending tasks from database")
                # Ensure processor is running
                await start_queue_processor()
            else:
                logger.info("No pending tasks found in database")

    except Exception as e:
        logger.error(f"Error restoring pending tasks: {e}")
