"""Real Store/Service + real subprocess fixture; no live authentication/model."""
import asyncio
from pathlib import Path
import sys

import pytest

from helperbot import codex_transport as transport
from helperbot.core import Denied, Scope, Store
from helperbot.service import Service


@pytest.mark.parametrize('action', ['delete_user', 'reset', 'disable', 'cancel'])
async def test_late_protocol_completion_cannot_resurrect_deleted_data(tmp_path, monkeypatch, action):
    monkeypatch.setattr(transport, 'require_supported_transport', lambda: None)
    fixture = Path(__file__).with_name('codex_protocol_fixture.py')
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(fixture)))
    completed, release = asyncio.Event(), asyncio.Event()
    processes = []
    original = transport.StdioClient.completion
    async def held_completion(client, *args):
        result = await original(client, *args)  # Exercise actual stream parsing first.
        processes.append(client.process)
        completed.set()
        await release.wait()
        return result
    monkeypatch.setattr(transport.StdioClient, 'completion', held_completion)
    store = Store(tmp_path / 'state.db')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path / 'runtime')
    task = asyncio.create_task(Service(store, adapter).ask(scope, 'synthetic question', 501))
    try:
        await asyncio.wait_for(completed.wait(), 2)
        if action == 'cancel':
            task.cancel()
        elif action == 'disable':
            store.configure(scope, False)
        else:
            getattr(store, action)(scope)
        release.set()
        with pytest.raises(asyncio.CancelledError if action == 'cancel' else Denied):
            await task
        assert processes[0].returncode is not None
        assert not list((tmp_path / 'runtime').glob('request-*'))
        if action in ('delete_user', 'disable'):
            assert store.knowledge(scope) == []
            assert store.history(scope) == []
            assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 0
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        store.close()
