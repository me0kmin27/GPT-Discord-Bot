"""Completion-boundary cancellation with real subprocesses and SQLite, no live AI."""
import asyncio
from pathlib import Path
import sys

import pytest

from helperbot.codex_transport import CodexOAuthProvider
from helperbot.core import Scope, Store
from helperbot.provider import Request
from helperbot.service import Service


class FixtureProvider(CodexOAuthProvider):
    def _command(self):
        return (sys.executable, str(Path(__file__).with_name('codex_protocol_fixture.py')))


async def find_child(name):
    # Bounded scheduler turns, not wall-clock sleeps or guessed subprocess timing.
    for _ in range(1000):
        child = next((t for t in asyncio.all_tasks()
                      if getattr(t.get_coro(), '__qualname__', '') == name), None)
        if child is not None:
            return child
        await asyncio.sleep(0)
    pytest.fail('owned child task never started: ' + name)


@pytest.mark.parametrize('boundary', ['provider', 'service', 'service_inner'])
async def test_completed_child_cancellation_propagates_without_persistence(tmp_path, boundary):
    store = Store(tmp_path / 'state.db')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    adapter = FixtureProvider(Path(sys.executable), tmp_path / 'runtime')
    operation = (adapter.answer(Request(scope.tenant, 'synthetic question', (), ()))
                 if boundary == 'provider' else
                 Service(store, adapter).ask(scope, 'synthetic question', 501))
    outer = asyncio.create_task(operation)
    accepted = []
    try:
        child = await find_child('CodexOAuthProvider.' +
                                 ('answer' if boundary == 'service' else '_answer'))
        def cancel_at_completion(completed):
            assert completed.done() and not completed.cancelled()
            accepted.append(outer.cancel())
        child.add_done_callback(cancel_at_completion)
        try:
            await outer
            propagated = False
        except asyncio.CancelledError:
            propagated = True
        assert accepted == [True], 'test must hit accepted completion-boundary cancellation'
        count = store.db.execute('SELECT COUNT(*) FROM generated_answers').fetchone()[0]
        assert (propagated, count) == (True, 0)
        assert not list((tmp_path / 'runtime').glob('request-*'))
    finally:
        if not outer.done():
            outer.cancel()
        await asyncio.gather(outer, return_exceptions=True)
        store.close()


@pytest.mark.parametrize('boundary', ['provider', 'service'])
@pytest.mark.parametrize('outcome', ['success', 'cancel', 'timeout'])
async def test_public_boundaries_settle_process_and_preserve_outcome(
        tmp_path, monkeypatch, boundary, outcome):
    processes = []
    spawned = asyncio.Event()
    original = asyncio.create_subprocess_exec
    async def observe_spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        spawned.set()
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', observe_spawn)
    class ScenarioProvider(FixtureProvider):
        def _command(self):
            return super()._command() + (('success' if outcome == 'success' else 'hang'),)
    store = Store(tmp_path / 'state.db')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    deadline = 0.2 if outcome == 'timeout' else 10
    adapter = ScenarioProvider(Path(sys.executable), tmp_path / 'runtime',
                               timeout=deadline if boundary == 'provider' else 10)
    operation = (adapter.answer(Request(scope.tenant, 'synthetic question', (), ()))
                 if boundary == 'provider' else
                 Service(store, adapter, timeout=deadline).ask(scope, 'synthetic question', 501))
    outer = asyncio.create_task(operation)
    try:
        await spawned.wait()
        if outcome == 'cancel':
            assert outer.cancel()
            with pytest.raises(asyncio.CancelledError):
                await outer
        elif outcome == 'timeout' and boundary == 'provider':
            with pytest.raises(asyncio.TimeoutError):
                await outer
        else:
            result = await outer
            if outcome == 'timeout':
                assert '공급자 시간 초과' in result.text
                assert 'fixture answer' not in result.text
            else:
                assert 'fixture answer, NOT live AI' in result.text
        count = store.db.execute('SELECT COUNT(*) FROM generated_answers').fetchone()[0]
        assert count == (1 if outcome == 'success' and boundary == 'service' else 0)
        assert processes and all(p.returncode is not None for p in processes)
        assert not list((tmp_path / 'runtime').glob('request-*'))
        if outcome == 'success':
            assert outer.cancel() is False  # Completed operations are not retroactively cancelled.
    finally:
        if not outer.done():
            outer.cancel()
        await asyncio.gather(outer, return_exceptions=True)
        store.close()


@pytest.mark.parametrize('initial', ['success', 'timeout'])
async def test_service_repeated_cancel_during_real_process_cleanup(tmp_path, monkeypatch, initial):
    from helperbot.codex_transport import StdioClient
    cleaning, release = asyncio.Event(), asyncio.Event()
    processes = []
    original = StdioClient._reap
    async def gated_reap(client):
        processes.append(client.process)
        cleaning.set()
        await release.wait()
        await original(client)
    monkeypatch.setattr(StdioClient, '_reap', gated_reap)
    class ScenarioProvider(FixtureProvider):
        def _command(self):
            return super()._command() + (('success' if initial == 'success' else 'hang'),)
    store = Store(tmp_path / 'state.db')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    adapter = ScenarioProvider(Path(sys.executable), tmp_path / 'runtime')
    outer = asyncio.create_task(Service(store, adapter,
        timeout=0.2 if initial == 'timeout' else 10).ask(scope, 'synthetic question', 501))
    try:
        await cleaning.wait()
        assert outer.cancel()
        await asyncio.sleep(0)
        assert not outer.done()
        assert outer.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await outer
        assert processes and all(p.returncode is not None for p in processes)
        assert not list((tmp_path / 'runtime').glob('request-*'))
        assert store.db.execute('SELECT COUNT(*) FROM generated_answers').fetchone()[0] == 0
    finally:
        release.set()
        if not outer.done():
            outer.cancel()
        await asyncio.gather(outer, return_exceptions=True)
        store.close()
