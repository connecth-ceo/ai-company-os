import asyncio
import os
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

ResultT = TypeVar("ResultT")
_state = threading.local()


def _worker_loop() -> asyncio.AbstractEventLoop:
    pid = os.getpid()
    loop = getattr(_state, "loop", None)
    owner_pid = getattr(_state, "pid", None)
    if owner_pid != pid or loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _state.loop = loop
        _state.pid = pid
    return loop


def run_worker_coroutine(coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Run all Celery work in one event loop per worker process and thread."""

    return _worker_loop().run_until_complete(coroutine)


def close_worker_async_runtime() -> None:
    loop = getattr(_state, "loop", None)
    if loop is not None and not loop.is_closed():
        loop.close()
    _state.loop = None
    _state.pid = None
