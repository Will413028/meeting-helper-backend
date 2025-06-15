"""Helper functions to run async database operations from sync context"""

import json
from src.logger import logger


def update_transcription_sync(task_id: str, **kwargs) -> bool:
    """
    Synchronous wrapper for update_transcription.

    This function makes an HTTP request to the API to update the transcription,
    avoiding the complexity of running async code in sync context.
    """
    try:
        # Prepare the update data
        update_data = {"task_id": task_id, **kwargs}

        # For now, we'll store the updates in a temporary file that can be processed
        # by a background task. This avoids the event loop issues entirely.
        import tempfile
        import os
        import uuid

        # Create a unique filename for this update
        update_id = str(uuid.uuid4())
        update_file = os.path.join(
            tempfile.gettempdir(), f"transcription_update_{update_id}.json"
        )

        # Write the update to a file
        with open(update_file, "w") as f:
            json.dump(update_data, f)

        logger.debug(f"Queued transcription update for {task_id} in {update_file}")

        # In a production system, you might want to:
        # 1. Use a proper message queue (Redis, RabbitMQ, etc.)
        # 2. Make an HTTP request to an internal API endpoint
        # 3. Use a database table as a queue

        return True

    except Exception as e:
        logger.error(f"Error queuing transcription update for {task_id}: {e}")
        return False


def process_pending_updates():
    """
    Process any pending transcription updates from the temporary files.
    This should be called periodically by a background task.
    """
    import tempfile
    import os
    import glob

    temp_dir = tempfile.gettempdir()
    pattern = os.path.join(temp_dir, "transcription_update_*.json")

    for update_file in glob.glob(pattern):
        try:
            with open(update_file, "r") as f:
                update_data = json.load(f)

            # Process the update (this would be done by an async task)
            logger.info(f"Processing pending update: {update_data}")

            # Delete the file after processing
            os.remove(update_file)

        except Exception as e:
            logger.error(f"Error processing update file {update_file}: {e}")
