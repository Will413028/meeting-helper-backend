"""Helper functions to run async database operations from sync context"""

import asyncio

from src.database import AsyncSessionLocal
from src.transcription.service import update_transcription as async_update_transcription


def update_transcription_sync(task_id: str, **kwargs) -> bool:
    """Synchronous wrapper for update_transcription"""

    async def _update():
        async with AsyncSessionLocal() as session:
            return await async_update_transcription(session, task_id, **kwargs)

    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_update())
    finally:
        loop.close()
