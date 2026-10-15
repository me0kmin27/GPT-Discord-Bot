"""Read-only operator guidance: synthetic service output only."""
import subprocess
import sys
from pathlib import Path
import pytest
from helperbot import settings_ops
from helperbot.manage import main


def test_direct_script_failure_explains_installed_entrypoint(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'helperbot' / 'manage.py'
    result = subprocess.run([sys.executable, str(script), 'start'], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert '-m helperbot.manage' in result.stderr
    assert 'sudo' in result.stderr
    assert 'Traceback' not in result.stderr



def test_cli_overview_is_read_only_and_actionable(monkeypatch, capsys):
    monkeypatch.setattr(settings_ops, 'operator_overview', lambda: {
        'applied': None, 'bot': {'unit': 'discord-helper.service', 'status': {'available': False},
                               'message': 'unavailable', 'command': None},
        'web': {'unit': 'discord-helper-web.service', 'status': {'available': False},
                'message': 'unavailable', 'command': None}})
    assert main(['overview']) == 0
    output = capsys.readouterr().out
    assert 'discord-helper-web.service' in output
    assert 'sudo' in output
    assert 'gui start' in output
    assert '127.0.0.1:8765' in output
    assert 'disabled' in output


def test_gui_overview_shows_two_services_and_access_guidance(tmp_path, monkeypatch):
    from test_settings_ops import paths_at
    from test_web_security import login, BASE, PASSWORD
    from helperbot.web_admin import create_app, bootstrap_admin
    paths = paths_at(tmp_path)
    bootstrap_admin(paths, PASSWORD)
    client = create_app(paths).test_client()
    assert client.get('/', base_url=BASE).status_code == 302
    login(client)
    page = client.get('/', base_url=BASE).get_data(as_text=True)
    assert 'discord-helper-web.service' in page
    assert 'ssh -N -L 8765:127.0.0.1:8765' in page
    assert 'disabled' in page
    assert '확인되지 않음' in page

def test_overview_separates_stopped_units_and_persistence():
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=(
            'ActiveState=inactive\nSubState=dead\nResult=success\n'
            'ExecMainStatus=0\nNRestarts=0\nLoadState=loaded\nUnitFileState=disabled\n'
            'Environment=synthetic-secret\n'), stderr='synthetic-secret')
    report = settings_ops.operator_overview(runner=runner)
    assert [call[3] for call in calls] == ['discord-helper.service', 'discord-helper-web.service']
    assert all(call[:3] == ['systemctl', '--user', 'show'] for call in calls)
    assert report['bot']['status']['UnitFileState'] == 'disabled'
    assert report['bot']['command'] == 'systemctl --user start discord-helper.service'
    assert report['web']['command'] == 'systemctl --user start discord-helper-web.service'
    assert report['applied'] is None
    assert 'synthetic-secret' not in str(report)


@pytest.mark.parametrize('load,active,expected', [
    ('not-found', 'inactive', None), ('masked', 'inactive', None),
    ('loaded', 'failed', 'restart'), ('loaded', 'active', None),
    ('loaded', 'activating', None), ('loaded', 'deactivating', None),
])
def test_guidance_never_starts_missing_masked_or_transitioning_units(load, active, expected):
    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=(
            f'LoadState={load}\nActiveState={active}\nSubState=dead\nResult=success\n'
            'ExecMainStatus=0\nNRestarts=0\nUnitFileState=disabled\n'))
    report = settings_ops.operator_overview(runner=runner)
    for key in ('bot', 'web'):
        command = report[key]['command']
        assert command == (f"systemctl --user {expected} {report[key]['unit']}" if expected else None)


@pytest.mark.parametrize('failure', ['missing', 'timeout', 'nonzero', 'malformed'])
def test_unavailable_output_is_private_and_not_stopped(failure):
    def runner(args, **kwargs):
        if failure == 'missing':
            raise OSError('synthetic-secret')
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(args, 10, output='synthetic-secret')
        return subprocess.CompletedProcess(args, 1 if failure == 'nonzero' else 0,
                                          stdout='ActiveState=synthetic-secret\n', stderr='synthetic-secret')
    report = settings_ops.operator_overview(runner=runner)
    assert 'synthetic-secret' not in str(report)
    assert report['bot']['status'] == {'available': False}
    assert report['web']['command'] is None


@pytest.mark.parametrize('unit', ['arbitrary.service', 'discord-helper.service; touch /tmp/no'])
def test_status_rejects_non_allowlisted_units(unit):
    with pytest.raises(ValueError):
        settings_ops.service_status(unit=unit, runner=lambda *a, **k: pytest.fail('executed'))
