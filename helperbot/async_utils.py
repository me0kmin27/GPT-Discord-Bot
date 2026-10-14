"""Owned-task deadlines with cancellation priority on Python 3.9 and later."""
import asyncio


class ObservedTimeout(asyncio.TimeoutError):
    """A child/native timeout observed at a known boundary, not budget expiry."""
    def __init__(self, stage, elapsed, timeout):
        super().__init__()
        self.stage = stage
        self.elapsed_ms = max(0, int(elapsed * 1000))
        self.deadline_ms = None if timeout is None else max(0, int(timeout * 1000))


class OwnedDeadlineExceeded(ObservedTimeout):
    """Only emitted when this application's own wait budget expires."""


async def wait_owned(awaitable, timeout, *, stage='wait'):
    """Wait with a deadline, then cancel/settle owned work before returning.

    Unlike older asyncio.wait_for, a completed child cannot turn an external
    cancellation into success. A child suppressing cancellation cannot turn a
    timeout into success either. Repeated caller cancellation cannot abandon
    cleanup; cancellation during cleanup takes priority over a timeout/error.
    """
    started = asyncio.get_running_loop().time()
    task = asyncio.ensure_future(awaitable)
    try:
        done, _ = await asyncio.wait((task,), timeout=timeout)
        if not done:
            raise OwnedDeadlineExceeded(stage, asyncio.get_running_loop().time() - started, timeout)
        try:
            return task.result()
        except (asyncio.TimeoutError, TimeoutError) as error:
            if isinstance(error, ObservedTimeout) or stage == 'wait':
                raise
            raise ObservedTimeout(stage, asyncio.get_running_loop().time() - started, timeout) from None
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
