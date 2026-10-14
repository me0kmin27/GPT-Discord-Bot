"""Synthetic protocol evidence, never authenticated inference."""
import sys
from pathlib import Path

from helperbot.codex_transport import CodexOAuthProvider
from helperbot.provider import Request, ProviderReply

FIXTURE = Path(__file__).with_name('codex_protocol_fixture.py')

async def test_empty_evidence_public_answer_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(CodexOAuthProvider, '_command',
                        lambda self: (sys.executable, str(FIXTURE), 'success'))
    adapter = CodexOAuthProvider(Path(sys.executable), tmp_path)
    reply = await adapter.answer(Request((1, 2), 'synthetic question', (), ()))
    assert reply == ProviderReply('fixture answer, NOT live AI', ())
    assert not list(tmp_path.glob('request-*'))


async def test_probe_refuses_without_explicit_live_opt_in(tmp_path, capsys):
    from helperbot import inference_probe
    assert inference_probe.main(['--data-dir', str(tmp_path)]) == 2
    import json
    record = json.loads(capsys.readouterr().out)
    assert record['stage'] == 'opt_in'
    assert record['answer_success'] is False
    assert list(tmp_path.iterdir()) == []


def test_probe_live_flag_calls_public_provider_with_empty_evidence(tmp_path, monkeypatch, capsys):
    import json
    from helperbot import inference_probe, provider
    class Synthetic:
        async def answer(self, request):
            import logging
            print('SECRET STDOUT')
            print('SECRET STDERR', file=sys.stderr)
            logging.error('SECRET LOG')
            assert request.evidence == request.history == ()
            assert request.question == 'What is two plus two? Reply briefly.'
            return ProviderReply('synthetic-secret-answer', ())
    monkeypatch.setattr(provider, 'build_provider', lambda *a, **kw: Synthetic())
    assert inference_probe.main(['--live', '--data-dir', str(tmp_path)]) == 0
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record['stage'] == 'complete'
    assert record['answer_success'] is True
    assert record['answer_length'] == len('synthetic-secret-answer')
    assert 0 <= record['duration_ms'] < 5000
    assert 'synthetic-secret' not in captured.out + captured.err
    assert captured.err == ''
    assert 'SECRET' not in captured.out


def test_probe_failure_is_safe_and_actionable(tmp_path, monkeypatch, capsys):
    import json
    from helperbot import inference_probe, provider
    class Synthetic:
        async def answer(self, request):
            raise provider.ProviderUnavailable('Codex managed ChatGPT login required')
    monkeypatch.setattr(provider, 'build_provider', lambda *a, **kw: Synthetic())
    assert inference_probe.main(['--live', '--data-dir', str(tmp_path)]) == 1
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record['category'] == 'login_required'
    assert record['stage'] == 'account'
    assert record['exception'] == 'ProviderUnavailable'
    assert record['answer_success'] is False
    assert record['answer_length'] == 0
    assert captured.err == ''


def test_untrusted_exception_never_stringified_or_exposed():
    from helperbot.inference_probe import safe_failure
    class SecretError(RuntimeError):
        def __str__(self):
            raise AssertionError('must never stringify')
    error = SecretError('SECRET AUTH BODY')
    error.code = True
    record = safe_failure(error)
    assert record['exception'] == 'Other'
    assert record['category'] == 'unknown'
    assert record['rpc_code'] is None
    assert 'SECRET' not in repr(record)


async def test_rpc_numeric_code_survives_without_message(tmp_path):
    import pytest
    from helperbot.codex_transport import StdioClient
    from helperbot.provider import ProviderUnavailable
    from helperbot.inference_probe import safe_failure
    async with StdioClient((sys.executable, str(FIXTURE), 'rpc_error'),
                           cwd=tmp_path, env={'CODEX_HOME': str(tmp_path)}) as client:
        with pytest.raises(ProviderUnavailable) as caught:
            await client.initialize()
    record = safe_failure(caught.value)
    assert record['rpc_code'] == -1
    assert 'synthetic-sensitive' not in repr(record)


async def test_service_failure_has_fixed_diagnostic_category(tmp_path):
    from helperbot.core import Store, Scope
    from helperbot.service import Service
    from helperbot.provider import ProviderUnavailable
    class Failing:
        async def answer(self, request):
            assert request.evidence == ()
            raise ProviderUnavailable('Codex managed ChatGPT login required')
    from contextlib import closing
    with closing(Store(tmp_path / 'state.db')) as store:
        scope = Scope(1, 10, 10, 100, admin=True)
        store.configure(scope, True)
        reply = await Service(store, Failing()).ask(scope, 'q', 501)
        assert '[account/login_required]' in reply.text


def test_cli_argument_errors_do_not_echo_untrusted_arguments(capsys):
    from helperbot.inference_probe import main
    assert main(['--SECRET-TOKEN']) == 2
    captured = capsys.readouterr()
    assert 'SECRET' not in captured.out + captured.err


def test_probe_rejects_invalid_empty_evidence_reply(tmp_path, monkeypatch, capsys):
    import json
    from helperbot import inference_probe, provider
    class Synthetic:
        async def answer(self, request):
            return ProviderReply('SECRET ANSWER', (123,))
    monkeypatch.setattr(provider, 'build_provider', lambda *a, **kw: Synthetic())
    assert inference_probe.main(['--live', '--data-dir', str(tmp_path)]) == 1
    record = json.loads(capsys.readouterr().out)
    assert record['category'] == 'response_rejected'
    assert record['answer_success'] is False
    assert record['answer_length'] == 0


async def test_generic_service_error_is_categorized_without_body(tmp_path):
    from contextlib import closing
    from helperbot.core import Store, Scope
    from helperbot.service import Service
    class Failing:
        async def answer(self, request):
            raise RuntimeError('SECRET EXCEPTION')
    with closing(Store(tmp_path / 'state.db')) as store:
        scope = Scope(1, 10, 10, 100, admin=True)
        store.configure(scope, True)
        reply = await Service(store, Failing()).ask(scope, 'q', 501)
        assert '[answer/unknown]' in reply.text
        assert 'SECRET' not in reply.text


def test_standalone_missing_install_has_no_traceback(tmp_path):
    import subprocess, json
    from helperbot import inference_probe
    result = subprocess.run([sys.executable, '-I', '-S', inference_probe.__file__,
                             '--live', '--data-dir', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stderr == ''
    assert json.loads(result.stdout)['category'] == 'installation_unavailable'


def test_probe_enforces_original_20_second_deadline(tmp_path, monkeypatch, capsys):
    import json
    from helperbot import inference_probe, provider, async_utils
    class Synthetic:
        async def answer(self, request):
            raise AssertionError('should not execute in this deadline wiring test')
    async def timeout(awaitable, seconds):
        assert seconds == 20
        awaitable.close()
        raise TimeoutError('SECRET TIMEOUT')
    monkeypatch.setattr(provider, 'build_provider', lambda *a, **kw: Synthetic())
    monkeypatch.setattr(async_utils, 'wait_owned', timeout)
    assert inference_probe.main(['--live', '--data-dir', str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)['category'] == 'timeout'
    assert 'SECRET' not in captured.out + captured.err


def test_probe_interrupt_is_sanitized(tmp_path, monkeypatch, capsys):
    import json
    from helperbot import inference_probe, provider
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt('SECRET INTERRUPT')
    monkeypatch.setattr(provider, 'build_provider', interrupt)
    assert inference_probe.main(['--live', '--data-dir', str(tmp_path)]) == 130
    captured = capsys.readouterr()
    assert captured.err == ''
    assert json.loads(captured.out)['category'] == 'cancelled'
    assert 'SECRET' not in captured.out
