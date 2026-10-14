from types import SimpleNamespace
import pytest
from helperbot.core import Store, Scope
from helperbot.service import Service
from helperbot.provider import ProviderUnavailable
from helperbot import manage as m
from helperbot.discord_app import create_client


async def test_provider_error_never_leaks_arbitrary_exception_details(tmp_path):
    s=Store(tmp_path/'state.db')
    who=Scope(1,10,10,100,admin=True)
    s.configure(who,True)
    class FailingProvider:
        async def answer(self,request):
            raise ProviderUnavailable('private-provider-detail-do-not-expose')
    answer=await Service(s,FailingProvider()).ask(who,'question',501)
    assert 'private-provider-detail' not in answer.text
    s.close()


async def test_gateway_error_handler_does_not_emit_event_content(tmp_path,capsys,caplog):
    store=Store(tmp_path/'state.db')
    client=create_client(store)
    try:
        raise RuntimeError('private-gateway-detail')
    except RuntimeError:
        await client.on_error('on_raw_message_delete')
    assert 'private-gateway-detail' not in caplog.text
    assert 'private-gateway-detail' not in capsys.readouterr().err
    await client.close()
    store.close()


def test_codex_login_child_has_restrictive_umask(tmp_path,monkeypatch):
    import os
    p=m.Paths(tmp_path/'config',tmp_path/'data',tmp_path/'units')
    monkeypatch.setattr(m.shutil,'which',lambda name:'/usr/bin/'+name)
    observed=[]
    def runner(*args,**kwargs):
        mask=os.umask(0o077)
        os.umask(mask)
        observed.append(mask)
        return SimpleNamespace(returncode=0)
    old=os.umask(0o022)
    try:
        m.codex_login(p,runner=runner)
        assert observed==[0o077]
    finally:
        os.umask(old)


def test_store_rejects_symlink_database(tmp_path):
    target=tmp_path/'target.db'
    target.write_text('do not open this file')
    link=tmp_path/'link.db'
    link.symlink_to(target)
    from helperbot.core import Denied
    with pytest.raises(Denied):
        Store(link)
    assert target.read_text()=='do not open this file'
