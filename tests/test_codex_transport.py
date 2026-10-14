"""Real subprocess IO with deterministic fixtures, never live model inference."""
import asyncio
from pathlib import Path
import sys

import pytest
from helperbot import provider

FIXTURE = Path(__file__).with_name('codex_protocol_fixture.py')


async def test_initialize_real_subprocess_and_reap(tmp_path):
    from helperbot.codex_transport import StdioClient
    async with StdioClient((sys.executable, str(FIXTURE)), cwd=tmp_path,
                           env={'CODEX_HOME': str(tmp_path)}) as client:
        result = await client.initialize()
        assert result['platformOs'] == 'fixture'
        process = client.process
        assert process.returncode is None
    assert process.returncode is not None


async def test_provider_security_gate_before_any_process_or_files(tmp_path):
    from helperbot.codex_transport import CodexOAuthProvider
    adapter = CodexOAuthProvider(tmp_path / 'absent-binary', tmp_path / 'data')
    with pytest.raises(provider.ProviderUnavailable, match='zero-tools'):
        await adapter.answer(provider.Request((1, 2), 'question', (), ()))
    assert list(tmp_path.iterdir()) == []


async def test_fresh_ephemeral_oauth_exchange_with_fixture_only(tmp_path, monkeypatch):
    from helperbot import codex_transport as transport
    # Test-only removal of the fixed gate; no shipped option can do this.
    monkeypatch.setattr(transport, 'require_supported_transport', lambda: None)
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(FIXTURE)))
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-secret-not-forwarded')
    monkeypatch.setenv('DISCORD_BOT_TOKEN', 'synthetic-secret-not-forwarded')
    adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path)
    request = provider.Request((1, 2), 'synthetic question', (),
                               ({'id': 7, 'question': 'q', 'solution': 's'},))
    for _ in range(2):
        reply = await adapter.answer(request)
        assert reply == provider.ProviderReply('fixture answer, NOT live AI', (7,))
    assert not list(tmp_path.glob('request-*'))


@pytest.mark.parametrize('scenario', ['server_request', 'rpc_error', 'wrong_id',
    'malformed', 'eof', 'oversized', 'notification_flood', 'unknown_notification',
    'wrong_version', 'remote_connected', 'early_tool', 'invalid_method', 'invalid_remote_params'])
async def test_protocol_failure_is_closed_sanitized_and_reaped(tmp_path, scenario, capsys):
    from helperbot.codex_transport import StdioClient
    async with StdioClient((sys.executable, str(FIXTURE), scenario), cwd=tmp_path,
                           env={'CODEX_HOME': str(tmp_path)}) as client:
        with pytest.raises(provider.ProviderUnavailable) as caught:
            await asyncio.wait_for(client.initialize(), 2)
        assert 'synthetic-sensitive' not in str(caught.value)
        process = client.process
    assert process.returncode is not None
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


async def test_official_remote_disabled_notification(tmp_path):
    from helperbot.codex_transport import StdioClient
    async with StdioClient((sys.executable, str(FIXTURE), 'remote_disabled'),
                           cwd=tmp_path, env={'CODEX_HOME': str(tmp_path)}) as client:
        assert (await client.initialize())['platformOs'] == 'fixture'


@pytest.mark.parametrize('scenario', ['tool_item', 'unknown_item', 'turn_approval',
    'wrong_thread', 'wrong_turn', 'bad_citation', 'bool_citation', 'invalid_output',
    'extra_output_field', 'excessive_output', 'stream_mismatch', 'no_final', 'failed_turn',
    'signed_out', 'api_key'])
async def test_stream_contract_fail_closed(tmp_path, monkeypatch, scenario):
    from helperbot import codex_transport as transport
    monkeypatch.setattr(transport, 'require_supported_transport', lambda: None)
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(FIXTURE), scenario))
    adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path, timeout=2)
    request = provider.Request((1, 2), 'synthetic question', (),
                               ({'id': 7, 'question': 'q', 'solution': 's'},))
    with pytest.raises(provider.ProviderUnavailable) as caught:
        await adapter.answer(request)
    assert 'synthetic-sensitive' not in str(caught.value)
    assert not list(tmp_path.glob('request-*'))


@pytest.mark.parametrize('changes', [
    {'question': 'x' * 2001}, {'history': ('q',) * 9},
    {'evidence': ({'id': 1, 'question': 'q', 'solution': 's'},) * 4},
    {'instruction': 'x' * 4097}, {'evidence': ({'id': True, 'question': 'q', 'solution': 's'},)},
    {'question': '😀' * 2000, 'history': ('😀' * 2000,) * 8}])
async def test_request_limits_before_files_or_process(tmp_path, monkeypatch, changes):
    from dataclasses import replace
    from helperbot import codex_transport as transport
    monkeypatch.setattr(transport, 'require_supported_transport', lambda: None)
    adapter = transport.CodexOAuthProvider(tmp_path / 'absent', tmp_path / 'data')
    request = replace(provider.Request((1, 2), 'q', (), ()), **changes)
    with pytest.raises(provider.ProviderUnavailable, match='request'):
        await adapter.answer(request)
    assert list(tmp_path.iterdir()) == []


def test_serialization_minimizes_evidence_and_separates_instruction():
    import json
    from helperbot.codex_transport import prepare_request
    request = provider.Request((1, 2), 'q', ('h',), ({'id': 7, 'question': 'q',
            'solution': 'untrusted instructions', 'guild': 1, 'author': 999,
            'source_message': 123},))
    payload = json.loads(prepare_request(request))
    assert payload == {'question': 'q', 'history': ['h'], 'evidence': [
        {'id': 7, 'question': 'q', 'solution': 'untrusted instructions'}]}
    assert request.instruction not in json.dumps(payload)


@pytest.mark.parametrize('during_spawn', [False, True])
async def test_cancellation_reaps_process_even_during_spawn(tmp_path, monkeypatch, during_spawn):
    from helperbot import codex_transport as transport
    created = asyncio.Event()
    release = asyncio.Event()
    processes = []
    original = asyncio.create_subprocess_exec
    async def spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        created.set()
        if during_spawn:
            await release.wait()
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    async def run():
        async with transport.StdioClient((sys.executable, str(FIXTURE), 'hang'),
                    cwd=tmp_path, env={'CODEX_HOME': str(tmp_path)}) as client:
            await client.initialize()
    task = asyncio.create_task(run())
    await asyncio.wait_for(created.wait(), 2)
    task.cancel()
    release.set()
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert processes[0].returncode is not None
    finally:
        # RED test cleanup must not leave the deliberately leaked fixture alive.
        if processes[0].returncode is None:
            processes[0].kill()
            await processes[0].wait()


async def test_client_deadline_is_not_unbounded(tmp_path):
    from helperbot.codex_transport import StdioClient
    async with StdioClient((sys.executable, str(FIXTURE), 'hang'), cwd=tmp_path,
             env={'CODEX_HOME': str(tmp_path)}, timeout=0.1) as client:
        with pytest.raises(asyncio.TimeoutError):
            await client.initialize()
        process = client.process
    assert process.returncode is not None


async def test_cancel_during_success_cleanup_not_swallowed(tmp_path, monkeypatch):
    from helperbot.codex_transport import StdioClient
    cleanup_started, release = asyncio.Event(), asyncio.Event()
    client = StdioClient((sys.executable, str(FIXTURE)), cwd=tmp_path,
                         env={'CODEX_HOME': str(tmp_path)})
    async def run():
        async with client:
            await client.initialize()
            original = client.process.wait
            async def slow_wait():
                cleanup_started.set()
                await release.wait()
                return await original()
            monkeypatch.setattr(client.process, 'wait', slow_wait)
    task = asyncio.create_task(run())
    await asyncio.wait_for(cleanup_started.wait(), 2)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.process.returncode is not None


async def test_cleanup_drains_saturated_stdout_after_kill(tmp_path):
    from helperbot.codex_transport import StdioClient
    client = StdioClient((sys.executable, str(FIXTURE), 'output_flood'),
                         cwd=tmp_path, env={'CODEX_HOME': str(tmp_path)})
    await client.__aenter__()
    with pytest.raises(provider.ProviderUnavailable):
        await client.initialize()
    # Deliberately let the pipe saturate before teardown; not a timing assumption
    # about inference. RED rescue drain ensures even a broken cleanup leaves no child.
    await asyncio.sleep(0.1)
    closing = asyncio.create_task(client.__aexit__())
    done, _ = await asyncio.wait((closing,), timeout=0.5)
    if not done:
        await client.process.stdout.read()
    await closing
    eof = client.process.stdout.at_eof()
    if not eof:
        await client.process.stdout.read()
    assert done and eof, 'cleanup left a paused stdout pipe open'
