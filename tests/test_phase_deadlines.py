"""Virtual monotonic clock + fake protocol; no network/auth/live inference."""
import asyncio
from contextlib import closing


import pytest

from helperbot import codex_transport as transport
from helperbot.core import Store, Scope
from helperbot.provider import ProviderReply, Request
from helperbot.service import Service
from helperbot.inference_probe import safe_failure
from test_codex_web_search import nested


def protocol_clock(monkeypatch, setup, generation, cleanup=0):
    loop = asyncio.get_running_loop()
    now = [loop.time()]
    monkeypatch.setattr(loop, 'time', lambda: now[0])
    phases = []
    async def advance(seconds):
        now[0] += seconds
        for _ in range(6):
            await asyncio.sleep(0)
    class Client:
        def __init__(self, command, *, cwd, **kwargs):
            self.cwd = cwd
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            phases.append('cleanup')
            await advance(cleanup)
        async def initialize(self):
            phases.append('initialize')
        async def rpc(self, method, params):
            phases.append(method)
            if method == 'config/read':
                return {'config': nested(transport.execution_config())}
            if method == 'account/read':
                return {'account': {'type': 'chatgpt'}}
            if method == 'thread/start':
                await advance(setup)
                return {'thread': {'id': 'synthetic', 'ephemeral': True, 'path': None},
                        'sandbox': {'type': 'readOnly', 'networkAccess': False},
                        'approvalPolicy': 'never', 'approvalsReviewer': 'user',
                        'cwd': str(self.cwd), 'modelProvider': 'openai'}
            assert method == 'turn/start'
            return {'turn': {'id': 'synthetic'}}
        async def completion(self, *args):
            phases.append('completion')
            await advance(generation)
            return ProviderReply('synthetic result', ())
    monkeypatch.setattr(transport, 'StdioClient', Client)
    return phases


async def test_full_phase_budgets_and_cleanup_not_cut_by_service_total_timer(tmp_path, monkeypatch):
    phases = protocol_clock(monkeypatch, 59, 239, cleanup=10)
    adapter = transport.CodexOAuthProvider('/synthetic/codex', tmp_path / 'runtime')
    with closing(Store(tmp_path / 'state.db')) as store:
        scope = Scope(1, 10, 10, 100, admin=True)
        store.configure(scope, True)
        answer = await Service(store, adapter).ask(scope, 'q', 501)
        assert 'synthetic result' in answer.text
        assert store.generated_answer(scope, answer.case) == 'synthetic result'
    assert phases == ['initialize', 'config/read', 'account/read', 'thread/start',
                      'turn/start', 'completion', 'cleanup']
    assert not list((tmp_path / 'runtime').glob('request-*'))


@pytest.mark.parametrize('setup,generation,stage,budget', [(61, 0, 'preparation', 60000),
                                                        (59, 241, 'generation', 240000),
                                                        (1, 241, 'generation', 240000)])
async def test_phase_overrun_has_own_budget_and_no_later_phase(tmp_path, monkeypatch, setup, generation, stage, budget):
    phases = protocol_clock(monkeypatch, setup, generation)
    adapter = transport.CodexOAuthProvider('/synthetic/codex', tmp_path)
    with pytest.raises(asyncio.TimeoutError) as caught:
        await adapter.answer(Request((1, 2), 'q', (), ()))
    record = safe_failure(caught.value)
    assert record['category'] == 'deadline_exceeded'
    assert record['stage'] == stage
    assert record['deadline_ms'] == budget
    assert record['elapsed_ms'] >= budget
    assert phases[-1] == 'cleanup'
    if stage == 'preparation':
        assert 'turn/start' not in phases
    assert not list(tmp_path.glob('request-*'))


def test_phase_defaults_and_config_are_not_forwarded_to_codex(tmp_path):
    adapter = transport.CodexOAuthProvider('/synthetic/codex', tmp_path)
    assert adapter.setup_timeout == 60
    assert adapter.timeout == 240
    assert adapter.setup_timeout + adapter.timeout == 300
    options = {'setup_timeout_seconds': 2, 'generation_timeout_seconds': 25}
    adapter = transport.CodexOAuthProvider('/synthetic/codex', tmp_path, options=options)
    assert adapter.setup_timeout == 2 and adapter.timeout == 25
    assert not any('timeout_seconds' in value for value in adapter._command())
    assert transport.DEFAULT_SETUP_TIMEOUT == 60
    assert transport.DEFAULT_GENERATION_TIMEOUT == 240


@pytest.mark.parametrize('key', ['setup_timeout_seconds', 'generation_timeout_seconds'])
@pytest.mark.parametrize('value', [True, '20', 0, -1, float('nan'), float('inf'), 241])
def test_phase_config_strict_validation(tmp_path, key, value):
    with pytest.raises(ValueError):
        transport.CodexOAuthProvider('/synthetic/codex', tmp_path, options={key: value})
