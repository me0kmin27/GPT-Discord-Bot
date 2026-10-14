"""Regression for the live-observed warning method, using synthetic IO only."""
import asyncio
import json
import sys
from pathlib import Path

import pytest
from helperbot.codex_transport import CodexOAuthProvider, StdioClient
from helperbot.provider import Request, ProviderUnavailable


@pytest.mark.parametrize('scenario', ['rpc_warning', 'turn_warning'])
async def test_warning_does_not_abort_empty_evidence_answer(tmp_path, monkeypatch, capsys, scenario):
    fixture = Path(__file__).with_name('codex_protocol_fixture.py')
    monkeypatch.setattr(CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(fixture), scenario))
    reply = await CodexOAuthProvider(Path(sys.executable), tmp_path).answer(
        Request((1, 2), 'synthetic question', (), ()))
    assert reply.text == 'fixture answer, NOT live AI' and reply.case_ids == ()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


async def receive(message):
    client = StdioClient((), cwd=None, env={})
    client.deadline = asyncio.get_running_loop().time() + 2
    class Process:
        stdout = asyncio.StreamReader()
    client.process = Process()
    client.process.stdout.feed_data(json.dumps(message).encode() + b'\n')
    return await client.receive()


@pytest.mark.parametrize('thread', [{}, {'threadId': None}, {'threadId': 't'}])
async def test_warning_body_is_discarded_but_thread_scope_preserved(thread):
    result = await receive({'method': 'warning', 'params': dict(thread, message='SECRET BODY')})
    assert 'SECRET' not in repr(result)
    assert result == {'method': 'warning', 'params': {'threadId': 't'} if thread.get('threadId') else {}}


@pytest.mark.parametrize('params', [{}, {'message': 3}, {'message': 'x', 'threadId': 3}])
async def test_malformed_warning_still_rejected(params):
    with pytest.raises(ProviderUnavailable):
        await receive({'method': 'warning', 'params': params})
