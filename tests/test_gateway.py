from types import SimpleNamespace
import pytest
from helperbot.core import Store, Scope
from helperbot.discord_app import create_client


@pytest.mark.parametrize('event,payload', [
    ('on_raw_message_delete', SimpleNamespace(guild_id=1,channel_id=10,message_id=502)),
    ('on_raw_bulk_message_delete', SimpleNamespace(guild_id=1,channel_id=10,message_ids={501,502})),
    ('on_guild_channel_delete', SimpleNamespace(guild=SimpleNamespace(id=1),id=10)),
    ('on_raw_thread_delete', SimpleNamespace(guild_id=1,thread_id=10)),
    ('on_guild_remove', SimpleNamespace(id=1)),
])
async def test_gateway_deletion_callbacks_purge_actual_store(tmp_path,event,payload):
    store=Store(tmp_path/'state.db')
    s=Scope(1,10,10,100,admin=True)
    store.configure(s,True)
    case=store.candidate(s,'question',501)
    store.resolve(s,case,'solution',502)
    client=create_client(store)
    assert hasattr(client,event), 'deletion callback missing'
    await getattr(client,event)(payload)
    assert store.knowledge(s)==[]
    await client.close()
    store.close()
