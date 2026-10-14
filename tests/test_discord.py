from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import importlib.util
import pytest
import discord
from helperbot.core import Store, Scope, Denied


def interaction(*, guild=1, channel=10, user=100, admin=False, moderator=False, private=False, thread=False):
    parent = MagicMock(spec=discord.TextChannel)
    parent.id = 10
    parent.guild = SimpleNamespace(id=guild)
    parent.permissions_for.return_value = discord.Permissions(view_channel=True, send_messages=True, manage_messages=moderator)
    ch = MagicMock(spec=discord.Thread if thread else discord.TextChannel)
    ch.id = channel
    ch.guild = SimpleNamespace(id=guild)
    ch.permissions_for.return_value = parent.permissions_for.return_value
    if thread:
        ch.parent = parent
        ch.is_private.return_value = private
    i = SimpleNamespace(guild_id=guild, guild=SimpleNamespace(id=guild), channel=ch,
                        user=SimpleNamespace(id=user, bot=False),
                        permissions=discord.Permissions(view_channel=True, send_messages=True, send_messages_in_threads=True, administrator=admin, manage_messages=moderator),
                        app_permissions=discord.Permissions(view_channel=True, send_messages=True, send_messages_in_threads=True),
                        response=SimpleNamespace(send_message=AsyncMock(), is_done=lambda: False),
                        original_response=AsyncMock(return_value=SimpleNamespace(id=501)),
                        edit_original_response=AsyncMock(), followup=SimpleNamespace(send=AsyncMock()))
    return i


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / 'state.db')
    yield s
    s.close()


def test_discord_tree_has_guild_only_commands_and_no_message_content_intent(store):
    assert importlib.util.find_spec('helperbot.discord_app'), 'Discord adapter missing'
    from helperbot.discord_app import create_client
    client = create_client(store)
    cmds = {c.name: c for c in client.tree.get_commands()}
    assert set(cmds) == {'ask', 'resolved', 'forget', 'reset', 'channel', 'privacy_delete'}
    assert all(c.guild_only for c in cmds.values())
    assert not client.intents.message_content
    assert not client.intents.members
    assert not hasattr(client, 'on_message')
    assert client.intents.guild_messages  # deletion metadata, not content
    assert list(client.cached_messages) == []
    assert client._connection._messages is None


def test_scope_normalizes_public_thread_and_rejects_dm_private_and_missing_permissions():
    assert importlib.util.find_spec('helperbot.discord_app'), 'Discord adapter missing'
    from helperbot.discord_app import scope_for
    assert scope_for(interaction(thread=True,channel=12)).tenant == (1,10)
    assert scope_for(interaction(thread=True,channel=12)).conversation == 12
    for bad in [interaction(guild=None), interaction(thread=True,private=True)]:
        with pytest.raises(Denied):
            scope_for(bad)
    bad = interaction()
    bad.permissions = discord.Permissions.none()
    with pytest.raises(Denied):
        scope_for(bad)


async def test_real_command_callbacks_full_local_flow(store):
    assert importlib.util.find_spec('helperbot.discord_app'), 'Discord adapter missing'
    from helperbot.discord_app import create_client
    client = create_client(store)
    commands = {c.name: c.callback for c in client.tree.get_commands()}
    await commands['channel'](interaction(admin=True), enabled=True, confirm_purge=False)
    first = interaction(thread=True,channel=12)
    await commands['ask'](first, question='전원 불량')
    first.edit_original_response.assert_awaited_once()
    assert '비활성' in first.edit_original_response.call_args.kwargs['content']
    case = store.db.execute('SELECT id FROM cases').fetchone()[0]
    confirmed = interaction(thread=True,channel=12)
    confirmed.original_response.return_value.id = 502
    await commands['resolved'](confirmed, case_id=str(case), solution='케이블 교체')
    assert store.knowledge(Scope(1,10,10,100))[0]['resolution_message'] == 502
    await commands['reset'](interaction(thread=True,channel=12))
    assert not store.history(Scope(1,10,12,100))
    await commands['forget'](interaction(admin=True), case_id=str(case), confirm=True)
    assert not store.knowledge(Scope(1,10,10,100))
    await commands['privacy_delete'](interaction(), confirm=True)
    await client.close()


async def test_adapter_denies_unauthorized_resolution_without_public_snippet(store):
    assert importlib.util.find_spec('helperbot.discord_app'), 'Discord adapter missing'
    from helperbot.discord_app import create_client
    client = create_client(store)
    store.configure(Scope(1,10,10,100,admin=True),True)
    case = store.candidate(Scope(1,10,10,100),'q',501)
    i = interaction(user=200)
    await client.tree.get_command('resolved').callback(i, case_id=str(case), solution='bad')
    assert i.response.send_message.call_args.kwargs['ephemeral'] is True
    assert store.knowledge(Scope(1,10,10,100)) == []
    await client.close()
