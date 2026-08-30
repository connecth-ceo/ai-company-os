import asyncio

from app.core.worker_async import close_worker_async_runtime, run_worker_coroutine


def test_worker_coroutines_reuse_one_event_loop_for_loop_bound_resources():
    close_worker_async_runtime()
    state: dict[str, object] = {}

    async def create_pending_future() -> int:
        loop = asyncio.get_running_loop()
        state["future"] = loop.create_future()
        return id(loop)

    async def resolve_pending_future() -> tuple[int, str]:
        loop = asyncio.get_running_loop()
        future = state["future"]
        assert isinstance(future, asyncio.Future)
        loop.call_soon(future.set_result, "done")
        return id(loop), await future

    try:
        first_loop_id = run_worker_coroutine(create_pending_future())
        second_loop_id, result = run_worker_coroutine(resolve_pending_future())
    finally:
        close_worker_async_runtime()

    assert second_loop_id == first_loop_id
    assert result == "done"
