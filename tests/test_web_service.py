from subprocess import CompletedProcess
import pytest
from helperbot.manage import ManagementError
from test_settings_ops import paths_at


def test_gui_unit_is_opt_in_fixed_loopback_and_idempotent(tmp_path, monkeypatch):
    from helperbot import web_service
    paths = paths_at(tmp_path)
    monkeypatch.setattr(web_service, 'require_systemd', lambda: None)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return CompletedProcess(args, 3 if 'is-active' in args else 0, '', '')
    assert web_service.gui_service(paths, 'install', runner=run) == 0
    unit = paths.units/'discord-helper-web.service'
    content = unit.read_text()
    assert 'gui run' in content and '8765' in content
    assert 'PrivateNetwork=true' not in content
    assert calls == [['systemctl', '--user', 'daemon-reload']]
    assert web_service.gui_service(paths, 'install', runner=run) == 0
    assert web_service.gui_service(paths, 'stop', runner=run) == 0
    assert calls[-1] == ['systemctl', '--user', 'is-active', '--quiet', 'discord-helper-web.service']
    with pytest.raises(ManagementError):
        web_service.gui_service(paths, 'restart;evil', runner=run)
