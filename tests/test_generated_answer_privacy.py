"""Generated-answer privacy through real callbacks; only provider/HTTP are fixtures."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from helperbot.core import Denied, Store
from helperbot.discord_app import create_client
from helperbot.service import Service
from test_discord import interaction
from test_generated_answers import SCOPE, TEXT, FixtureProvider
from test_generated_answer_limits import store


class GatedFixture(FixtureProvider):
    def __init__(self):
        super().__init__()
        self.started, self.release = asyncio.Event(), asyncio.Event()

    async def answer(self, request):
        self.started.set()
        await self.release.wait()
        return await super().answer(request)


async def purge(client, event, evidence):
    if event == 'reset':
        await client.tree.get_command('reset').callback(interaction(thread=True, channel=12))
    elif event == 'forget':
        await client.tree.get_command('forget').callback(interaction(admin=True), case_id='all', confirm=True)
    elif event == 'privacy':
        await client.tree.get_command('privacy_delete').callback(interaction(), confirm=True)
    elif event == 'resolver_privacy':
        await client.tree.get_command('privacy_delete').callback(interaction(user=300), confirm=True)
    elif event == 'disable':
        await client.tree.get_command('channel').callback(interaction(admin=True), enabled=False, confirm_purge=True)
        await client.tree.get_command('channel').callback(interaction(admin=True), enabled=True)
    elif event == 'thread':
        await client.on_raw_thread_delete(SimpleNamespace(guild_id=1, thread_id=12))
    elif event == 'channel':
        await client.on_guild_channel_delete(SimpleNamespace(guild=SimpleNamespace(id=1), id=10))
    elif event == 'guild':
        await client.on_guild_remove(SimpleNamespace(id=1))
    elif event == 'bulk':
        await client.on_raw_bulk_message_delete(SimpleNamespace(guild_id=1, channel_id=12, message_ids={501}))
    elif event == 'receipt':
        await client.on_raw_message_delete(SimpleNamespace(guild_id=1, channel_id=12, message_id=501))
    elif event == 'evidence':
        await client.on_raw_message_delete(SimpleNamespace(guild_id=1, channel_id=13, message_id=601))
    else:
        raise AssertionError(event)


@pytest.mark.parametrize('event', ['reset', 'forget', 'privacy', 'resolver_privacy', 'disable',
                                  'thread', 'channel', 'guild', 'receipt', 'bulk', 'evidence'])
@pytest.mark.parametrize('during_provider', [True, False])
async def test_gateway_and_commands_cancel_late_saves_or_purge_committed_drafts(store, monkeypatch, event, during_provider):
    fixture = GatedFixture()
    monkeypatch.setattr('helperbot.discord_app.DisabledCodex', lambda: fixture)
    client = create_client(store)
    source_scope = replace(SCOPE, conversation=13, user=200)
    evidence = store.candidate(source_scope, 'capacitor source', 600)
    store.resolve(replace(source_scope, user=300, moderator=True), evidence, 'human capacitor fix', 601)
    i = interaction(thread=True, channel=12)
    task = asyncio.create_task(client.tree.get_command('ask').callback(i, question='capacitor question'))
    await asyncio.wait_for(fixture.started.wait(), 2)
    if during_provider:
        await purge(client, event, evidence)
    fixture.release.set()
    await asyncio.wait_for(task, 2)
    assert [row['id'] for row in fixture.requests[0].evidence] == [evidence]
    if during_provider:
        i.edit_original_response.assert_not_awaited()
    else:
        i.edit_original_response.assert_awaited_once()
        assert store.db.execute('SELECT count(*) FROM generated_answers').fetchone()[0] == 1
        await purge(client, event, evidence)
    retained = int(not during_provider and event == 'reset')
    assert store.db.execute('SELECT count(*) FROM generated_answers').fetchone()[0] == retained
    assert store.db.execute('SELECT count(*) FROM generated_answer_sources').fetchone()[0] == retained
    assert not store._pending
    assert store.db.execute('PRAGMA foreign_key_check').fetchall() == []
    await client.close()


@pytest.mark.parametrize('changes', [dict(guild=2), dict(channel=20), dict(user=999)])
async def test_unrelated_privacy_operations_do_not_cancel_other_drafts(store, changes):
    fixture = GatedFixture()
    task = asyncio.create_task(Service(store, fixture).ask(SCOPE, 'question', 501))
    await asyncio.wait_for(fixture.started.wait(), 2)
    other = replace(SCOPE, **changes)
    if 'channel' in changes:
        store.forget(other)
    else:
        store.delete_user(other)
    fixture.release.set()
    result = await task
    assert store.generated_answer(SCOPE, result.case) == TEXT


async def test_task_cancellation_does_not_save_partial_output(store):
    fixture = GatedFixture()
    task = asyncio.create_task(Service(store, fixture).ask(SCOPE, 'question', 501))
    await asyncio.wait_for(fixture.started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not store._pending
    assert store.db.execute('SELECT count(*) FROM generated_answers').fetchone()[0] == 0


@pytest.mark.parametrize('target', ['candidate', 'evidence'])
async def test_independent_connection_deletion_is_rechecked_before_save(tmp_path, target):
    path = tmp_path / 'state.db'
    store = Store(path)
    store.configure(SCOPE, True)
    source_scope = replace(SCOPE, user=200)
    evidence = store.candidate(source_scope, 'capacitor', 600)
    store.resolve(source_scope, evidence, 'human capacitor fix', 601)
    other = Store(path)
    fixture = GatedFixture()
    task = asyncio.create_task(Service(store, fixture).ask(SCOPE, 'capacitor', 501))
    await asyncio.wait_for(fixture.started.wait(), 2)
    other.delete_user(SCOPE if target == 'candidate' else source_scope)
    fixture.release.set()
    with pytest.raises(Denied):
        await task
    assert [row['id'] for row in fixture.requests[0].evidence] == [evidence]
    assert store.db.execute('SELECT count(*) FROM generated_answers').fetchone()[0] == 0
    assert store.db.execute('PRAGMA foreign_key_check').fetchall() == []
    other.close()
    store.close()
    reopened = Store(path)
    assert reopened.db.execute('SELECT count(*) FROM generated_answers').fetchone()[0] == 0
    reopened.close()


def test_competing_connection_save_and_delete_never_resurrects_a_case(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path = tmp_path / 'race.db'
    store = Store(path)
    store.configure(SCOPE, True)
    case = store.candidate(SCOPE, 'question', 501)
    store.close()
    ready = Barrier(2)
    def worker(save):
        connection = Store(path)
        try:
            ready.wait(timeout=5)
            if save:
                with connection.operation(SCOPE) as pending:
                    try:
                        connection.save_generated_answer(SCOPE, case, TEXT, pending)
                    except Denied:
                        return 'deleted first'
                return 'saved first'
            connection.delete_user(SCOPE)
            return 'deleted'
        finally:
            connection.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        saved, deleted = list(pool.map(worker, [True, False]))
    assert saved in ('deleted first', 'saved first')
    assert deleted == 'deleted'
    store = Store(path)
    for table in ('cases', 'generated_answers', 'generated_answer_sources'):
        assert store.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
    assert store.db.execute('PRAGMA foreign_key_check').fetchall() == []
    store.close()


async def test_uncited_selected_evidence_is_still_privacy_tracked(store):
    source_scope = replace(SCOPE, user=200)
    evidence = store.candidate(source_scope, 'capacitor', 600)
    store.resolve(source_scope, evidence, 'human capacitor fix', 601)
    class UncitedFixture(FixtureProvider):
        async def answer(self, request):
            self.requests.append(request)
            from helperbot.provider import ProviderReply
            return ProviderReply(TEXT, ())
    fixture = UncitedFixture()
    result = await Service(store, fixture).ask(SCOPE, 'capacitor', 501)
    assert [row['id'] for row in fixture.requests[0].evidence] == [evidence]
    assert store.generated_answer(SCOPE, result.case) == TEXT
    store.delete_user(source_scope)
    assert store.generated_answer(SCOPE, result.case) is None
