from pathlib import Path
from types import SimpleNamespace
import os
import pytest
from helperbot import manage as m


def paths(tmp_path):
    return m.Paths(tmp_path/'config',tmp_path/'data',tmp_path/'units')


def test_install_renders_private_user_unit_idempotently_without_secrets(tmp_path,monkeypatch):
    assert hasattr(m,'install'), 'systemd installation missing'
    p=paths(tmp_path)
    calls=[]
    def runner(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(m.platform,'system',lambda:'Linux')
    monkeypatch.setattr(m.shutil,'which',lambda name:'/usr/bin/'+name)
    m.install(p,runner=runner)
    unit=p.units/'discord-helper.service'
    first=unit.read_text()
    assert 'UMask=0077' in first
    assert 'NoNewPrivileges=true' in first
    assert 'helperbot.manage' in first
    assert ' run' in first
    assert 'DISCORD_BOT_TOKEN' not in first
    assert unit.stat().st_mode & 0o777 == 0o600
    m.install(p,runner=runner)
    assert unit.read_text()==first
    assert calls==[['systemctl','--user','daemon-reload']]*2
    unit.write_text('[Service]\nExecStart=/somebody-elses-service\n')
    with pytest.raises(m.ManagementError):
        m.install(p,runner=runner)


@pytest.mark.parametrize('action', ['start','stop','restart','status','logs'])
def test_systemd_lifecycle_invokes_real_commands_and_verifies_state(tmp_path,monkeypatch,action):
    assert hasattr(m,'lifecycle'), 'lifecycle missing'
    p=paths(tmp_path)
    calls=[]
    def runner(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=3 if action=='stop' and 'is-active' in args else 0)
    monkeypatch.setattr(m.platform,'system',lambda:'Linux')
    monkeypatch.setattr(m.shutil,'which',lambda name:'/usr/bin/'+name)
    assert m.lifecycle(p,action,runner=runner)==0
    assert '--user' in calls[0]
    assert 'discord-helper.service' in calls[0]
    if action in ('start','stop','restart'):
        assert calls[1]==['systemctl','--user','is-active','--quiet','discord-helper.service']
    if action=='logs':
        assert calls[0][0]=='journalctl'


def test_start_reports_failed_state_readback(tmp_path,monkeypatch):
    assert hasattr(m,'lifecycle'), 'lifecycle missing'
    monkeypatch.setattr(m.platform,'system',lambda:'Linux')
    monkeypatch.setattr(m.shutil,'which',lambda name:'/usr/bin/'+name)
    def runner(args,**kwargs):
        return SimpleNamespace(returncode=3 if 'is-active' in args else 0)
    assert m.lifecycle(paths(tmp_path),'start',runner=runner)!=0


def test_codex_login_is_official_device_flow_with_isolated_home(tmp_path,monkeypatch):
    assert hasattr(m,'codex_login'), 'Codex login delegation missing'
    monkeypatch.setattr(m.shutil,'which',lambda name:'/usr/bin/'+name)
    monkeypatch.setenv('OPENAI_API_KEY','unit-test-must-not-propagate')
    monkeypatch.setenv('CODEX_HOME','/must/not/reuse/personal-auth')
    calls=[]
    def runner(args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(returncode=0)
    p=paths(tmp_path)
    assert m.codex_login(p,runner=runner)==0
    argv,kw=calls[0]
    assert argv==['/usr/bin/codex','-c','cli_auth_credentials_store="file"','-c','forced_login_method="chatgpt"','login','--device-auth']
    assert kw['env']['HOME']==str(p.data/'login-home')
    assert kw['cwd']==p.data/'login-home'
    assert kw['env']['CODEX_HOME']==str(p.data/'codex')
    assert 'OPENAI_API_KEY' not in kw['env']
    assert 'capture_output' not in kw
    assert (p.data/'codex').stat().st_mode & 0o777==0o700


def test_codex_installer_uses_user_prefix_no_sudo_or_global_install(tmp_path,monkeypatch):
    assert hasattr(m,'install_codex'), 'Codex installer missing'
    monkeypatch.setattr(m.shutil,'which',lambda name:'/usr/bin/'+name)
    calls=[]
    def runner(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    p=paths(tmp_path)
    assert m.install_codex(p,runner=runner)==0
    assert calls[0]==['/usr/bin/npm','install','--prefix',str(p.data/'tools'),'--no-audit','--no-fund','@openai/codex@0.162.1']
    assert '-g' not in calls[0]


def test_systemd_path_escaping_prevents_directive_injection(tmp_path):
    assert hasattr(m,'unit_text'), 'unit generator missing'
    with pytest.raises(m.ManagementError):
        m.unit_text(m.Paths(tmp_path/'bad\nExecStart=evil',tmp_path/'data',tmp_path/'units'))
    text=m.unit_text(m.Paths(tmp_path/'space dir',tmp_path/'percent%dir',tmp_path/'units'))
    assert 'percent%%dir' in text
    assert '"' in text
