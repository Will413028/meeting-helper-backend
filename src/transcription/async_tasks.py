"""Async task handling for transcription updates"""

import asyncio
from typing import Optional

from src.database import AsyncSessionLocal
from src.transcription.service import update_transcription as async_update_transcription
from src.logger import logger


class TranscriptionUpdateQueue:
    """Queue for handling transcription updates asynchronously"""

    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.running = False

    async def start(self):
        """Start the worker task"""
        if not self.running:
            self.running = True
            self.worker_task = asyncio.create_task(self._worker())
            logger.info("TranscriptionUpdateQueue worker started")

    async def stop(self):
        """Stop the worker task"""
        self.running = False
        if self.worker_task:
            # Put a None to wake up the worker
            await self.queue.put(None)
            await self.worker_task
            logger.info("TranscriptionUpdateQueue worker stopped")

    async def _worker(self):
        """Worker that processes update requests"""
        while self.running:
            try:
                # Get update request from queue
                update_request = await self.queue.get()

                if update_request is None:
                    # Shutdown signal
                    break

                task_id = update_request.get("task_id")
                kwargs = update_request.get("kwargs", {})

                # Process the update
                async with AsyncSessionLocal() as session:
                    try:
                        await async_update_transcription(session, task_id, **kwargs)
                        logger.debug(f"Successfully updated transcription {task_id}")
                    except Exception as e:
                        logger.error(f"Error updating transcription {task_id}: {e}")

            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(1)  # Brief pause before continuing

    async def enqueue_update(self, task_id: str, **kwargs):
        """Add an update request to the queue"""
        await self.queue.put({"task_id": task_id, "kwargs": kwargs})


# Global update queue instance
update_queue = TranscriptionUpdateQueue()


async def enqueue_transcription_update(task_id: str, **kwargs):
    """Enqueue a transcription update"""
    await update_queue.enqueue_update(task_id, **kwargs)
