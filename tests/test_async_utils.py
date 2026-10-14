"""Deterministic deadline/cancellation scheduling; compatible with Python 3.9."""
import asyncio

import pytest

from helperbot.async_utils import wait_owned


@pytest.mark.parametrize('outcome', ['result', 'error', 'cancel'])
async def test_owned_completion_without_external_cancel(outcome):
    async def child():
        if outcome == 'error':
            raise ValueError('synthetic')
        if outcome == 'cancel':
            raise asyncio.CancelledError()
        return 42
    if outcome == 'result':
        assert await wait_owned(child(), 1) == 42
    else:
        with pytest.raises(ValueError if outcome == 'error' else asyncio.CancelledError):
            await wait_owned(child(), 1)


@pytest.mark.parametrize('outcome', ['result', 'error'])
@pytest.mark.parametrize('order', ['cancel_first', 'complete_first'])
async def test_completion_and_caller_cancel_same_turn(outcome, order):
    release = asyncio.Event()
    async def child():
        await release.wait()
        if outcome == 'error':
            raise ValueError('synthetic')
        return 42
    task = asyncio.create_task(child())
    outer = asyncio.create_task(wait_owned(task, 10))
    await asyncio.sleep(0)  # Both tasks are waiting, with callbacks registered.
    accepted = []
    if order == 'complete_first':
        task.add_done_callback(lambda _: accepted.append(outer.cancel()))
        release.set()
    else:
        accepted.append(outer.cancel())
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await outer
    assert accepted == [True]
    assert task.done()


@pytest.mark.parametrize('suppress_cancel', [False, True])
async def test_genuine_timeout_settles_child_even_if_it_returns(suppress_cancel):
    started, finished = asyncio.Event(), asyncio.Event()
    async def child():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if suppress_cancel:
                return 'too late'
            raise
        finally:
            finished.set()
    task = asyncio.create_task(child())
    await started.wait()
    with pytest.raises(asyncio.TimeoutError):
        await wait_owned(task, 0)
    assert finished.is_set() and task.done()


@pytest.mark.parametrize('initial', ['timeout', 'cancel'])
async def test_repeated_cancel_during_settlement_wins_and_waits(initial):
    started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def child():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
    task = asyncio.create_task(child())
    await started.wait()
    outer = asyncio.create_task(wait_owned(task, 0 if initial == 'timeout' else 10))
    await asyncio.sleep(0)
    if initial == 'cancel':
        assert outer.cancel()
    await cleaning.wait()
    assert outer.cancel()
    await asyncio.sleep(0)
    assert not outer.done() and not task.done()
    assert outer.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await outer
    assert task.done()
