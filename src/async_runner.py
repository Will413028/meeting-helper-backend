"""Async runner for executing async functions in sync contexts safely"""

import asyncio
import threading
from typing import Any, Coroutine, Optional, TypeVar

T = TypeVar("T")


class AsyncRunner:
    """Thread-safe async runner that maintains a single event loop per thread"""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._started = False

    def _run_event_loop(self):
        """Run the event loop in a separate thread"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self):
        """Start the async runner"""
        with self._lock:
            if self._started:
                return

            self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self._thread.start()

            # Wait for the loop to be ready
            while self._loop is None:
                threading.Event().wait(0.01)

            self._started = True

    def run_async(self, coro: Coroutine[Any, Any, T]) -> T:
        """Run an async coroutine and return the result"""
        if not self._started:
            self.start()

        if self._loop is None:
            raise RuntimeError("Event loop not initialized")

        # Schedule the coroutine in the event loop
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def stop(self):
        """Stop the async runner and clean up"""
        with self._lock:
            if not self._started or self._loop is None:
                return

            # Stop the event loop
            self._loop.call_soon_threadsafe(self._loop.stop)

            # Wait for the thread to finish
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=5)

            # Close the loop
            if not self._loop.is_closed():
                self._loop.close()

            self._loop = None
            self._thread = None
            self._started = False


# Global async runner for background tasks
_background_runner = AsyncRunner()


def run_async_in_background(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine in the background thread's event loop"""
    return _background_runner.run_async(coro)


def cleanup_background_runner():
    """Clean up the background async runner"""
    _background_runner.stop()
