import uuid
from datetime import datetime
from typing import Dict, Optional
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
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
        }


class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, TranscriptionTask] = {}

    def create_task(self, filename: str) -> str:
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = TranscriptionTask(task_id, filename)
        return task_id

    def get_task(self, task_id: str) -> Optional[TranscriptionTask]:
        return self.tasks.get(task_id)

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

    def complete_task(self, task_id: str, result: Dict):
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            task.progress = 100
            task.result = result
            task.current_step = "Completed"

    def fail_task(self, task_id: str, error_message: str):
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.error_message = error_message
            task.current_step = "Failed"

    def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task and task.status in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            task.current_step = "Cancelled"
            return True
        return False


# Global task manager instance
task_manager = TaskManager()
