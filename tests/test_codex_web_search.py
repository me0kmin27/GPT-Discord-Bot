"""Offline pinned-protocol web search tests; never authenticated inference."""
import json
from pathlib import Path
import sys

import pytest
from helperbot import codex_transport as transport, provider


def nested(flat):
    result = {}
    for key, value in flat.items():
        dest = result
        parts = key.split('.')
        for part in parts[:-1]:
            dest = dest.setdefault(part, {})
        dest[parts[-1]] = value
    return result


def test_explicit_search_configuration_preserves_local_restrictions(tmp_path):
    options = {'web_search': 'live', 'model': 'operator-model', 'model_reasoning_effort': 'low'}
    adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path, options=options)
    config = transport.execution_config(options)
    assert config['web_search'] == 'live'
    assert config['model'] == 'operator-model'
    assert config['model_reasoning_effort'] == 'low'
    assert config['sandbox_mode'] == 'read-only'
    assert config['approval_policy'] == 'never'
    assert config['features.shell_tool'] is False
    assert config['features.browser_use'] is False
    assert config['mcp_servers'] == {}
    assert 'web_search="live"' in adapter._command()
    transport.validate_config(nested(config), options)
    with pytest.raises(provider.ProviderUnavailable):
        transport.validate_config(nested(config))
    assert transport.execution_config()['web_search'] == 'disabled'


@pytest.mark.parametrize('options', [[], {'shell_tool': True}, {'web_search': True},
    {'web_search': 'cached'}, {'model': ''}, {'model': 'x\ny'},
    {'model_reasoning_effort': False}, {'model': 'x' * 129}])
def test_operator_options_are_narrow_and_validated(options, tmp_path):
    with pytest.raises(ValueError):
        transport.CodexOAuthProvider(Path(sys.executable), tmp_path, options=options)


def test_web_protocol_errors_retain_safe_diagnostic_categories(tmp_path):
    from helperbot.inference_probe import safe_failure
    client = transport.StdioClient((), cwd=tmp_path, env={}, web_search=True)
    with pytest.raises(provider.ProviderUnavailable) as caught:
        client.checked_item({'type': 'webSearch', 'id': 'sensitive'})
    assert safe_failure(caught.value)['category'] == 'tool_item_rejected'


def test_nonsecret_operator_example_is_valid(tmp_path):
    example = json.loads((Path(__file__).parents[1] / 'examples/runtime.codex-web-search.json').read_text())
    assert example['codex'] == {'web_search': 'live', 'model': 'gpt-6.1-sol',
                                'model_reasoning_effort': 'low',
                                'setup_timeout_seconds': 60, 'generation_timeout_seconds': 240}
    assert transport.validate_options(example['codex']) == example['codex']


def test_runtime_options_reach_provider(tmp_path, monkeypatch):
    from helperbot import manage
    paths = manage.Paths(tmp_path / 'config', tmp_path / 'data', tmp_path / 'units')
    paths.config.mkdir(mode=0o700)
    options = {'web_search': 'live', 'model': 'operator-model', 'model_reasoning_effort': 'low',
               'setup_timeout_seconds': 60, 'generation_timeout_seconds': 240}
    target = paths.config / 'runtime.json'
    target.write_text(json.dumps({'provider': 'codex-oauth', 'sync_guild': 123, 'codex': options}))
    target.chmod(0o600)
    seen = []
    class Client:
        class tree:
            @staticmethod
            def get_commands():
                return []
        async def close(self):
            pass
    def create(store, **kwargs):
        seen.append(kwargs['provider'])
        return Client()
    monkeypatch.setattr(manage, 'create_client', create)
    assert manage.run(paths, check=True, codex_executable=Path(sys.executable)) == 0
    assert seen[0].options == options
    assert seen[0].setup_timeout == 60
    assert seen[0].timeout == 240


@pytest.mark.parametrize('scenario', ['web_success', 'web_open', 'web_find', 'web_other', 'web_no_sources'])
async def test_hosted_search_progress_is_not_answer(tmp_path, monkeypatch, capsys, scenario):
    fixture = Path(__file__).with_name('codex_protocol_fixture.py')
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(fixture), scenario))
    adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path, options={'web_search': 'live'})
    reply = await adapter.answer(provider.Request((1, 2), 'synthetic question', (), ()))
    assert reply.case_ids == ()
    assert len(reply.text) <= 1000
    if scenario == 'web_no_sources':
        assert 'No web sources supplied' in reply.text
    else:
        assert 'https://example.com/weather' in reply.text
        assert 'not independently verified' in reply.text
    assert 'synthetic-sensitive' not in reply.text
    assert not list(tmp_path.glob('request-*'))
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('scenario', ['web_bad_action', 'web_bad_query', 'web_wrong_scope',
    'web_local', 'web_request', 'web_no_search'])
async def test_web_search_failures_are_closed_and_private(tmp_path, monkeypatch, capsys, scenario):
    fixture = Path(__file__).with_name('codex_protocol_fixture.py')
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(fixture), scenario))
    adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path, options={'web_search': 'live'})
    with pytest.raises(provider.ProviderUnavailable) as caught:
        await adapter.answer(provider.Request((1, 2), 'synthetic question', (), ()))
    assert 'synthetic-sensitive' not in str(caught.value)
    assert not list(tmp_path.glob('request-*'))
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('sources', [None, 'https://example.com', [True], ['file:///secret'],
    ['https://name:password@example.com'], ['https://example.com/\nsecret'],
    ['https://example.com'] * 2, ['https://example.com/' + 'x' * 512],
    ['https://a.example', 'https://b.example', 'https://c.example', 'https://d.example']])
def test_malformed_model_citations_rejected(sources):
    with pytest.raises(ValueError):
        transport.render_web_sources({'text': 'answer', 'web_sources': sources}, True)


@pytest.mark.parametrize('scenario', ['web_success', 'web_no_sources', 'web_bad_action'])
async def test_empty_case_evidence_search_storage_and_failure_fallback(tmp_path, monkeypatch, scenario):
    from helperbot.core import Scope, Store
    from helperbot.service import Service
    fixture = Path(__file__).with_name('codex_protocol_fixture.py')
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(fixture), scenario))
    store = Store(tmp_path / 'state.db')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    try:
        adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path / 'runtime',
                                               options={'web_search': 'live'})
        answer = await Service(store, adapter).ask(scope, 'synthetic question', 501)
        assert answer.evidence == ()
        row = store.db.execute('SELECT status FROM cases WHERE id=?', (answer.case,)).fetchone()
        assert row['status'] == 'candidate'
        generated = store.generated_answer(scope, answer.case)
        if scenario == 'web_bad_action':
            assert generated is None
            assert '생성 답변 없음' in answer.text
        else:
            assert 0 < len(generated) <= 1000
            assert generated in answer.text
            assert ('not independently verified' if scenario == 'web_success'
                    else 'No web sources supplied') in generated
        assert store.knowledge(scope) == []
    finally:
        store.close()


async def test_cancel_during_web_search_reaps_without_output(tmp_path, monkeypatch, capsys):
    import asyncio
    fixture = Path(__file__).with_name('codex_protocol_fixture.py')
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(fixture), 'web_hang'))
    searching = asyncio.Event()
    processes = []
    receive = transport.StdioClient.receive
    async def observe(client):
        event = await receive(client)
        if event.get('method') == 'item/started' and event['params']['item']['type'] == 'webSearch':
            processes.append(client.process)
            searching.set()
        return event
    monkeypatch.setattr(transport.StdioClient, 'receive', observe)
    adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path, options={'web_search': 'live'})
    task = asyncio.create_task(adapter.answer(provider.Request((1, 2), 'synthetic question', (), ())))
    try:
        await asyncio.wait_for(searching.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert processes[0].returncode is not None
        assert not list(tmp_path.glob('request-*'))
        assert capsys.readouterr() == ('', '')
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_citation_rendering_does_not_overflow_storage_or_assert_verification():
    with pytest.raises(ValueError):
        transport.render_web_sources({'text': 'x' * 999, 'web_sources': ['https://example.com']}, True)
    with pytest.raises(ValueError):
        transport.render_web_sources({'text': 'answer', 'web_sources': ['https://example.com']}, False)


@pytest.mark.parametrize('kind', ['commandExecution', 'fileChange', 'mcpToolCall',
    'dynamicToolCall', 'imageView', 'functionCallOutput', 'unknown'])
def test_non_web_items_never_accepted_when_search_enabled(tmp_path, kind):
    client = transport.StdioClient((), cwd=tmp_path, env={}, web_search=True)
    with pytest.raises(provider.ProviderUnavailable):
        client.checked_item({'type': kind, 'id': 'sensitive'})


def test_web_results_discarded_before_queue_not_promoted_to_citations(tmp_path):
    client = transport.StdioClient((), cwd=tmp_path, env={}, web_search=True)
    item = {'type': 'webSearch', 'id': 'web', 'query': 'private query',
            'action': {'type': 'search', 'queries': ['private query']},
            'results': [{'url': 'https://example.com', 'snippet': 'sensitive', 'future': []}]}
    assert client.checked_item(item) == {'type': 'webSearch', 'id': 'web'}
    client.web_search = False
    with pytest.raises(provider.ProviderUnavailable):
        client.checked_item(item)


@pytest.mark.parametrize('change', [{'action': []}, {'action': {'type': 'search', 'queries': [1]}},
    {'action': {'type': 'findInPage', 'pattern': []}}, {'id': []}, {'results': {}},
    {'status': 'completed'}, {'query': False}])
def test_malformed_web_envelope_rejected(tmp_path, change):
    client = transport.StdioClient((), cwd=tmp_path, env={}, web_search=True)
    item = dict({'type': 'webSearch', 'id': 'web', 'query': '', 'action': None}, **change)
    with pytest.raises(provider.ProviderUnavailable):
        client.checked_item(item)
