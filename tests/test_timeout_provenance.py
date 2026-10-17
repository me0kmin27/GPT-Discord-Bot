"""Offline deterministic timeout provenance, not evidence of a live timeout."""
import asyncio
from contextlib import closing

import pytest

from helperbot.async_utils import wait_owned
from helperbot.inference_probe import safe_failure
from helperbot.core import Store, Scope
from helperbot.service import Service


async def test_owned_deadline_is_distinct_from_immediate_child_timeout():
    async def pending():
        await asyncio.Event().wait()
    with pytest.raises(asyncio.TimeoutError) as caught:
        await wait_owned(pending(), 0)
    own = safe_failure(caught.value)
    assert own['category'] == 'deadline_exceeded'
    assert own['timeout_origin'] == 'owned'
    assert own['deadline_ms'] == 0
    assert own['elapsed_ms'] >= 0

    for error in (asyncio.TimeoutError('SECRET'), TimeoutError('SECRET')):
        async def immediate():
            raise error
        with pytest.raises(type(error)) as child:
            await wait_owned(immediate(), 20)
        assert child.value is error
        record = safe_failure(child.value)
        assert record['timeout_origin'] == 'child_or_native'
        assert record['deadline_ms'] is None
        assert 'SECRET' not in repr(record)


@pytest.mark.parametrize('error_type', [asyncio.TimeoutError, TimeoutError])
async def test_service_immediate_timeout_does_not_claim_owned_deadline(tmp_path, error_type):
    class Failing:
        async def answer(self, request):
            raise error_type('SECRET PROMPT AUTH ANSWER')
    with closing(Store(tmp_path / 'state.db')) as store:
        scope = Scope(1, 10, 10, 100, admin=True)
        store.configure(scope, True)
        result = await Service(store, Failing(), timeout=20).ask(scope, 'q', 501)
        assert '[service/timeout]' in result.text
        assert '내부 시간 초과' in result.text
        assert 'deadline_ms=20000' in result.text
        assert 'elapsed_ms=' in result.text
        assert '/resolved' not in result.text
        assert 'SECRET' not in result.text


@pytest.mark.parametrize('layer', ['preparation', 'transport'])
async def test_nested_layer_owns_only_its_actual_deadline(tmp_path, monkeypatch, layer):
    from helperbot.codex_transport import CodexOAuthProvider, StdioClient
    from helperbot.provider import Request
    if layer == 'preparation':
        obj = CodexOAuthProvider('/synthetic/codex', tmp_path)
        # Zero budget through test injection; production defaults stay 60/240.
        obj.setup_timeout = 0
        async def blocked(*args):
            await asyncio.Event().wait()
        monkeypatch.setattr(obj, '_prepare', blocked)
        invoke = lambda: obj.answer(Request((1, 2), 'q', (), ()))
    else:
        obj = StdioClient((), cwd=tmp_path, env={})
        obj.deadline = asyncio.get_running_loop().time()
        invoke = lambda: obj._bounded(asyncio.Event().wait())
    with pytest.raises(asyncio.TimeoutError) as caught:
        await invoke()
    record = safe_failure(caught.value)
    assert record['stage'] == layer
    assert record['category'] == 'deadline_exceeded'


@pytest.mark.parametrize('error_type', [asyncio.TimeoutError, TimeoutError])
async def test_provider_native_timeout_not_rewritten_as_transport_unavailable(tmp_path, monkeypatch, error_type):
    from helperbot.codex_transport import CodexOAuthProvider
    from helperbot.provider import Request
    obj = CodexOAuthProvider('/synthetic/codex', tmp_path)
    error = error_type('SECRET')
    async def immediate(*args):
        raise error
    monkeypatch.setattr(obj, '_answer', immediate)
    with pytest.raises(error_type) as caught:
        await obj.answer(Request((1, 2), 'q', (), ()))
    assert caught.value is error


async def test_immediate_preparation_timeout_has_phase_budget_not_expiry(tmp_path, monkeypatch):
    from helperbot.codex_transport import CodexOAuthProvider
    from helperbot.provider import Request
    adapter = CodexOAuthProvider('/synthetic/codex', tmp_path)
    async def immediate(*args):
        raise TimeoutError('SECRET')
    monkeypatch.setattr(adapter, '_prepare', immediate)
    with pytest.raises((asyncio.TimeoutError, TimeoutError)) as caught:
        await adapter.answer(Request((1, 2), 'q', (), ()))
    record = safe_failure(caught.value)
    assert record['stage'] == 'preparation'
    assert record['timeout_origin'] == 'child_or_native'
    assert record['category'] == 'timeout'
    assert record['deadline_ms'] == 60000
    assert 0 <= record['elapsed_ms'] < 60000
    assert 'SECRET' not in repr(record)


async def test_discord_initial_ack_failure_never_enters_provider(tmp_path):
    from unittest.mock import AsyncMock
    from test_discord import interaction
    from helperbot.discord_app import create_client
    with closing(Store(tmp_path / 'state.db')) as store:
        store.configure(Scope(1, 10, 10, 100, admin=True), True)
        provider = type('Synthetic', (), {'answer': AsyncMock()})()
        client = create_client(store, provider=provider)
        i = interaction()
        i.response.send_message.side_effect = TimeoutError('SECRET')
        try:
            with pytest.raises(TimeoutError):
                await client.tree.get_command('ask').callback(i, question='q')
            provider.answer.assert_not_awaited()
            i.edit_original_response.assert_not_awaited()
            assert store.db.execute('SELECT COUNT(*) FROM cases').fetchone()[0] == 0
        finally:
            await client.close()
