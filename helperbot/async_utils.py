"""Owned-task deadlines with cancellation priority on Python 3.9 and later."""
import asyncio


async def wait_owned(awaitable, timeout):
    """Wait with a deadline, then cancel/settle owned work before returning.

    Unlike older asyncio.wait_for, a completed child cannot turn an external
    cancellation into success. A child suppressing cancellation cannot turn a
    timeout into success either. Repeated caller cancellation cannot abandon
    cleanup; cancellation during cleanup takes priority over a timeout/error.
    """
    task = asyncio.ensure_future(awaitable)
    try:
        done, _ = await asyncio.wait((task,), timeout=timeout)
        if not done:
            raise asyncio.TimeoutError()
        return task.result()
    finally:
        if not task.done():
            task.cancel()
        # Retrieve even an already-completed child's exception when cancellation
        # wins the race. Shield settlement, never the provider's actual work.
        settled = asyncio.gather(task, return_exceptions=True)
        cancelled = False
        while not settled.done():
            try:
                await asyncio.shield(settled)
            except asyncio.CancelledError:
                cancelled = True
        settled.result()
        if cancelled:
            raise asyncio.CancelledError()
