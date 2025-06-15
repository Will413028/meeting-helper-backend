import uuid
from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum
import asyncio


class TaskStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranscriptionTask:
    def __init__(self, task_id: str, filename: str):
        self.task_id = task_id
        self.filename = filename
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.result: Optional[Dict] = None
        self.estimated_completion_time: Optional[datetime] = None
        self.current_step: str = "Waiting to start"
        self.queue_position: Optional[int] = None

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "status": self.status.value,
            "progress": self.progress,
            "current_step": self.current_step,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "estimated_completion_time": self.estimated_completion_time.isoformat()
            if self.estimated_completion_time
            else None,
            "error_message": self.error_message,
            "result": self.result,
            "queue_position": self.queue_position,
        }


class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, TranscriptionTask] = {}
        self.task_queue: List[str] = []  # Queue of task IDs waiting to be processed
        self.current_processing_task: Optional[str] = None  # Currently processing task
        self._queue_lock = asyncio.Lock()

    def create_task(self, filename: str) -> str:
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = TranscriptionTask(task_id, filename)
        return task_id

    def get_task(self, task_id: str) -> Optional[TranscriptionTask]:
        return self.tasks.get(task_id)

    async def add_to_queue(self, task_id: str):
        """Add task to processing queue"""
        async with self._queue_lock:
            if (
                task_id not in self.task_queue
                and task_id != self.current_processing_task
            ):
                self.task_queue.append(task_id)
                task = self.get_task(task_id)
                if task:
                    task.status = TaskStatus.QUEUED
                    task.queue_position = len(self.task_queue)
                    task.current_step = f"Queued (position {task.queue_position})"

    async def get_next_task(self) -> Optional[str]:
        """Get next task from queue if no task is currently processing"""
        async with self._queue_lock:
            if self.current_processing_task is None and self.task_queue:
                task_id = self.task_queue.pop(0)
                self.current_processing_task = task_id

                # Update queue positions for remaining tasks
                for i, queued_task_id in enumerate(self.task_queue):
                    queued_task = self.get_task(queued_task_id)
                    if queued_task:
                        queued_task.queue_position = i + 1
                        queued_task.current_step = f"Queued (position {i + 1})"

                return task_id
            return None

    async def is_processing_available(self) -> bool:
        """Check if processing slot is available"""
        async with self._queue_lock:
            return self.current_processing_task is None

    def update_task_progress(
        self,
        task_id: str,
        progress: int,
        current_step: str,
        estimated_completion_time: Optional[datetime] = None,
    ):
        task = self.get_task(task_id)
        if task:
            task.progress = progress
            task.current_step = current_step
            if estimated_completion_time:
                task.estimated_completion_time = estimated_completion_time

    def start_task(self, task_id: str):
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.PROCESSING
            task.started_at = datetime.now()
            task.queue_position = None

    async def complete_task(self, task_id: str, result: Dict):
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.progress = 100
            task.result = result
            task.current_step = "Completed"

        # Release processing slot
        async with self._queue_lock:
            if self.current_processing_task == task_id:
                self.current_processing_task = None

    async def fail_task(self, task_id: str, error_message: str):
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.error_message = error_message
            task.current_step = "Failed"

        # Release processing slot
        async with self._queue_lock:
            if self.current_processing_task == task_id:
                self.current_processing_task = None

    async def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task and task.status in [
            TaskStatus.PENDING,
            TaskStatus.QUEUED,
            TaskStatus.PROCESSING,
        ]:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            task.current_step = "Cancelled"

            # Remove from queue if queued
            async with self._queue_lock:
                if task_id in self.task_queue:
                    self.task_queue.remove(task_id)
                    # Update queue positions
                    for i, queued_task_id in enumerate(self.task_queue):
                        queued_task = self.get_task(queued_task_id)
                        if queued_task:
                            queued_task.queue_position = i + 1
                            queued_task.current_step = f"Queued (position {i + 1})"

                # Release processing slot if this was the current task
                if self.current_processing_task == task_id:
                    self.current_processing_task = None

            return True
        return False

    def get_queue_status(self) -> Dict:
        """Get current queue status"""
        return {
            "current_processing": self.current_processing_task,
            "queue_length": len(self.task_queue),
            "queued_tasks": self.task_queue.copy(),
        }


# Global task manager instance
task_manager = TaskManager()
