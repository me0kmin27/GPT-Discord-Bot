import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
from helperbot import manage as m


def invoke(tmp_path,*args):
    return subprocess.run([sys.executable,'-m','helperbot.manage','--config-dir',str(tmp_path/'config'),'--data-dir',str(tmp_path/'data'),'--unit-dir',str(tmp_path/'units'),*args],env={'PATH':os.defpath},capture_output=True,text=True)


def test_management_cli_help_and_doctor_are_real_offline_commands(tmp_path):
    result=invoke(tmp_path,'--help')
    assert 'codex-login' in result.stdout
    result=invoke(tmp_path,'doctor')
    assert result.returncode==0
    assert 'disabled-codex' in result.stdout
    assert 'credentials_present=False' in result.stdout
    assert not (tmp_path/'config').exists()


def test_management_run_check_never_needs_credentials(tmp_path):
    result=invoke(tmp_path,'run','--check')
    assert result.returncode==0,result.stderr
    assert '6 commands' in result.stdout
    assert (tmp_path/'data'/'state.db').exists()
    assert not (tmp_path/'config'/'credentials.json').exists()


def test_foreground_runtime_uses_private_token_without_leaking_it(tmp_path,monkeypatch,capsys):
    assert hasattr(m,'run'), 'foreground runtime missing'
    p=m.Paths(tmp_path/'config',tmp_path/'data',tmp_path/'units')
    m.setup(p,token='unit-test-token')
    calls=[]
    class Client:
        def run(self,token,**kwargs):
            calls.append(token)
    monkeypatch.setattr(m,'create_client',lambda *a,**kw:Client())
    assert m.run(p)==0
    assert calls==['unit-test-token']
    assert 'unit-test-token' not in capsys.readouterr().out


def test_single_runtime_lock_prevents_concurrent_instances(tmp_path):
    assert hasattr(m,'runtime_lock'), 'single process guard missing'
    p=m.Paths(tmp_path/'config',tmp_path/'data',tmp_path/'units')
    with m.runtime_lock(p):
        with pytest.raises(m.ManagementError):
            with m.runtime_lock(p):
                pass
    with m.runtime_lock(p):
        pass
