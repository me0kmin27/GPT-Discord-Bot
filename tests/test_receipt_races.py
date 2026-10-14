"""Exercise real command/event callbacks with only Discord HTTP replaced."""
from types import SimpleNamespace

import pytest

from helperbot.core import Scope
from helperbot.discord_app import create_client
from test_discord import interaction, store  # shared HTTP fixtures / real SQLite


@pytest.mark.parametrize('boundary', ['send_message', 'original_response'])
@pytest.mark.parametrize('bulk', [False, True])
async def test_ask_deleted_receipt_before_insert(store, boundary, bulk):
    client = create_client(store)
    scope = Scope(1, 10, 12, 100, admin=True)
    store.configure(scope, True)
    i = interaction(thread=True, channel=12)

    async def delete_during_http(*args, **kwargs):
        i.response.is_done = lambda: True
        payload = SimpleNamespace(guild_id=1, channel_id=12,
                                  message_id=501, message_ids={501})
        callback = (client.on_raw_bulk_message_delete if bulk
                    else client.on_raw_message_delete)
        await callback(payload)
        return SimpleNamespace(id=501)

    target = i.response if boundary == 'send_message' else i
    getattr(target, boundary).side_effect = delete_during_http
    await client.tree.get_command('ask').callback(i, question='deleted question')
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 0
    assert store.history(scope) == []
    i.edit_original_response.assert_not_awaited()
    await client.close()


@pytest.mark.parametrize('boundary', ['send_message', 'original_response'])
@pytest.mark.parametrize('bulk', [False, True])
async def test_resolved_deleted_receipt_before_update(store, boundary, bulk):
    client = create_client(store)
    scope = Scope(1, 10, 12, 100, admin=True)
    store.configure(scope, True)
    case = store.candidate(scope, 'question', 501)
    i = interaction(thread=True, channel=12)
    i.original_response.return_value.id = 502

    async def delete_during_http(*args, **kwargs):
        i.response.is_done = lambda: True
        payload = SimpleNamespace(guild_id=1, channel_id=12,
                                  message_id=502, message_ids={502})
        callback = (client.on_raw_bulk_message_delete if bulk
                    else client.on_raw_message_delete)
        await callback(payload)
        return SimpleNamespace(id=502)

    target = i.response if boundary == 'send_message' else i
    getattr(target, boundary).side_effect = delete_during_http
    await client.tree.get_command('resolved').callback(
        i, case_id=str(case), solution='deleted solution')
    assert store.knowledge(scope) == []
    row = store.db.execute('SELECT * FROM cases WHERE id=?', (case,)).fetchone()
    assert row['status'] == 'candidate'
    assert row['solution'] is None and row['resolution_message'] is None
    i.edit_original_response.assert_not_awaited()
    await client.close()


@pytest.mark.parametrize('boundary', ['send_message', 'original_response'])
@pytest.mark.parametrize('command', ['ask', 'resolved'])
async def test_privacy_delete_invalidates_initial_receipt(store, boundary, command):
    client = create_client(store)
    scope = Scope(1, 10, 12, 100, admin=True)
    store.configure(scope, True)
    # Moderator resolution must also be cancelled when the resolver deletes data,
    # even though the resolver is not linked to the candidate yet.
    case = store.candidate(Scope(1, 10, 12, 200), 'other question', 500)
    i = interaction(thread=True, channel=12, moderator=True)

    async def privacy_during_http(*args, **kwargs):
        i.response.is_done = lambda: True
        await client.tree.get_command('privacy_delete').callback(
            interaction(channel=99), confirm=True)
        return SimpleNamespace(id=501)

    target = i.response if boundary == 'send_message' else i
    getattr(target, boundary).side_effect = privacy_during_http
    kwargs = ({'question': 'old submission'} if command == 'ask'
              else {'case_id': str(case), 'solution': 'old solution'})
    await client.tree.get_command(command).callback(i, **kwargs)
    rows = store.db.execute('SELECT * FROM cases').fetchall()
    assert len(rows) == 1 and rows[0]['author'] == 200
    assert rows[0]['status'] == 'candidate'
    assert store.history(scope) == []
    i.edit_original_response.assert_not_awaited()
    # Cancellation is not a permanent ban: a new operation succeeds.
    fresh = interaction(thread=True, channel=12)
    await client.tree.get_command('ask').callback(fresh, question='fresh submission')
    fresh.edit_original_response.assert_awaited_once()
    assert store.history(scope) == ['fresh submission']
    assert not store._pending
    await client.close()


@pytest.mark.parametrize('event', ['reset', 'forget', 'disable_enable', 'thread', 'channel', 'guild'])
@pytest.mark.parametrize('reenable', [False, True])
async def test_purge_invalidates_initial_ask_even_if_reenabled(store, event, reenable):
    client = create_client(store)
    scope = Scope(1, 10, 12, 100, admin=True)
    store.configure(scope, True)
    i = interaction(thread=True, channel=12)

    async def purge(*args, **kwargs):
        i.response.is_done = lambda: True
        if event == 'reset':
            await client.tree.get_command('reset').callback(interaction(thread=True, channel=12))
        elif event == 'forget':
            await client.tree.get_command('forget').callback(interaction(admin=True), case_id='all', confirm=True)
        elif event == 'disable_enable':
            await client.tree.get_command('channel').callback(interaction(admin=True), enabled=False, confirm_purge=True)
        elif event == 'thread':
            await client.on_raw_thread_delete(SimpleNamespace(guild_id=1, thread_id=12))
        elif event == 'channel':
            await client.on_guild_channel_delete(SimpleNamespace(guild=SimpleNamespace(id=1), id=10))
        else:
            await client.on_guild_remove(SimpleNamespace(id=1))
        # Re-enablement cannot make an older submission valid again.
        if reenable:
            store.configure(scope, True)

    i.response.send_message.side_effect = purge
    await client.tree.get_command('ask').callback(i, question='old question')
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 0
    assert store.history(scope) == []
    i.edit_original_response.assert_not_awaited()
    assert not store._pending
    await client.close()


@pytest.mark.parametrize('event', ['other_guild', 'other_channel', 'other_user', 'own_receipt', 'evidence', 'privacy', 'thread_evidence'])
async def test_deletion_during_service_is_scoped_and_suppresses_stale_output(store, event):
    import asyncio
    client = create_client(store)
    scope = Scope(1, 10, 12, 100, admin=True)
    store.configure(scope, True)
    evidence_scope = Scope(1, 10, 13, 200)
    evidence = store.candidate(evidence_scope, 'evidence question', 600)
    store.resolve(evidence_scope, evidence, 'evidence solution', 601)
    i = interaction(thread=True, channel=12)
    tasks = []

    async def disrupt():
        if event.startswith('other'):
            who = {'other_guild': interaction(guild=2),
                   'other_channel': interaction(channel=20, admin=True),
                   'other_user': interaction(user=300)}[event]
            name = 'forget' if event == 'other_channel' else 'privacy_delete'
            kwargs = {'case_id': 'all', 'confirm': True} if name == 'forget' else {'confirm': True}
            await client.tree.get_command(name).callback(who, **kwargs)
        elif event == 'privacy':
            await client.tree.get_command('privacy_delete').callback(interaction(user=200), confirm=True)
        elif event == 'thread_evidence':
            await client.on_raw_thread_delete(SimpleNamespace(guild_id=1, thread_id=13))
        else:
            await client.on_raw_message_delete(SimpleNamespace(
                guild_id=1, channel_id=12 if event == 'own_receipt' else 13,
                message_id=501 if event == 'own_receipt' else 601))

    async def receipt():
        # Event cannot run until the real service yields at its provider await.
        tasks.append(asyncio.create_task(disrupt()))
        return SimpleNamespace(id=501)

    i.original_response.side_effect = receipt
    i.response.is_done = lambda: True
    await client.tree.get_command('ask').callback(i, question='new question')
    await asyncio.gather(*tasks)
    if event.startswith('other'):
        i.edit_original_response.assert_awaited_once()
    else:
        i.edit_original_response.assert_not_awaited()
    assert not store._pending
    await client.close()


@pytest.mark.parametrize('command', ['ask', 'resolved'])
@pytest.mark.parametrize('event', ['guild_message', 'channel_message', 'sibling_message', 'guild_privacy', 'other_user', 'unknown_message'])
async def test_initial_receipt_cancellation_is_scoped(store, command, event):
    client = create_client(store)
    scope = Scope(1, 10, 12, 100, admin=True)
    store.configure(scope, True)
    case = store.candidate(scope, 'question', 500)
    i = interaction(thread=True, channel=12)

    async def disrupt(*args, **kwargs):
        i.response.is_done = lambda: True
        if event in ('guild_privacy', 'other_user'):
            await client.tree.get_command('privacy_delete').callback(
                interaction(guild=2 if event == 'guild_privacy' else 1,
                            user=100 if event == 'guild_privacy' else 200), confirm=True)
        else:
            await client.on_raw_message_delete(SimpleNamespace(
                guild_id=2 if event == 'guild_message' else 1,
                channel_id={'channel_message': 20, 'sibling_message': 13}.get(event, 12),
                message_id=999 if event == 'unknown_message' else 501))
        return SimpleNamespace(id=501)

    i.original_response.side_effect = disrupt
    kwargs = {'question': 'new question'} if command == 'ask' else {'case_id': str(case), 'solution': 'solution'}
    await client.tree.get_command(command).callback(i, **kwargs)
    if event == 'unknown_message':
        # Deliberate fail-closed tradeoff until the receipt ID is known.
        i.edit_original_response.assert_not_awaited()
        assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 1
        assert store.knowledge(scope) == []
    else:
        i.edit_original_response.assert_awaited_once()
    assert not store._pending
    await client.close()


@pytest.mark.parametrize('command', ['ask', 'resolved'])
@pytest.mark.parametrize('boundary', ['send_message', 'original_response', 'edit_original_response'])
@pytest.mark.parametrize('cancel', [False, True])
async def test_pending_registration_released_on_http_failure_or_task_cancellation(store, command, boundary, cancel):
    import asyncio
    client = create_client(store)
    scope = Scope(1, 10, 12, 100, admin=True)
    store.configure(scope, True)
    case = store.candidate(scope, 'question', 500)
    i = interaction(thread=True, channel=12)
    error = asyncio.CancelledError if cancel else RuntimeError
    target = i.response if boundary == 'send_message' else i
    getattr(target, boundary).side_effect = error('synthetic transport failure')
    kwargs = {'question': 'new question'} if command == 'ask' else {'case_id': str(case), 'solution': 'solution'}
    with pytest.raises(error):
        await client.tree.get_command(command).callback(i, **kwargs)
    assert not store._pending
    if boundary != 'edit_original_response':
        assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 1
        assert store.knowledge(scope) == []
    # Deletion events outside an active operation retain no tombstones.
    for message in range(1000, 1100):
        await client.on_raw_message_delete(SimpleNamespace(guild_id=1, channel_id=12, message_id=message))
    assert not store._pending
    await client.close()
