"""Real callback/SQLite quota boundary tests; only Discord HTTP is mocked."""
import pytest
from helperbot.core import Scope
from helperbot.discord_app import create_client
from test_discord import interaction, store


async def test_full_tenant_rejected_before_public_receipt(store, monkeypatch):
    store.cases_per_tenant = 1
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    store.candidate(scope, 'existing', 500)
    monkeypatch.setenv('HELPER_ADMISSION_USER_REQUESTS', '1')
    client = create_client(store)
    denied = interaction(thread=True, channel=12)
    await client.tree.get_command('ask').callback(denied, question='private overflow')
    denied.response.send_message.assert_awaited_once()
    assert denied.response.send_message.call_args.kwargs.get('ephemeral') is True
    assert 'embed' not in denied.response.send_message.call_args.kwargs
    denied.original_response.assert_not_awaited()
    denied.edit_original_response.assert_not_awaited()
    assert not store._pending
    # Capacity rejection does not consume the rate budget or block cleanup.
    await client.tree.get_command('privacy_delete').callback(interaction(), confirm=True)
    fresh = interaction()
    await client.tree.get_command('ask').callback(fresh, question='fresh')
    fresh.edit_original_response.assert_awaited_once()
    await client.close()


@pytest.mark.parametrize('boundary', ['send_message', 'original_response'])
async def test_capacity_filled_during_receipt_denies_persistence_and_releases_admission(store, boundary):
    from types import SimpleNamespace
    store.cases_per_tenant = 1
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    client = create_client(store)
    losing = interaction()
    losing.response.is_done = lambda: True

    async def fill(*args, **kwargs):
        store.candidate(Scope(1, 10, 12, 200), 'winner', 600)
        return SimpleNamespace(id=501)

    target = losing.response if boundary == 'send_message' else losing
    getattr(target, boundary).side_effect = fill
    await client.tree.get_command('ask').callback(losing, question='loser')
    losing.edit_original_response.assert_not_awaited()
    assert losing.followup.send.call_args.kwargs['ephemeral'] is True
    assert store.history(scope) == []
    assert store.db.execute('SELECT question FROM cases').fetchone()[0] == 'winner'
    assert not store._pending
    assert not store.db.in_transaction
    await client.tree.get_command('forget').callback(interaction(admin=True), case_id='all', confirm=True)
    fresh = interaction()
    await client.tree.get_command('ask').callback(fresh, question='fresh')
    fresh.edit_original_response.assert_awaited_once()
    await client.close()


@pytest.mark.parametrize('cleanup', ['privacy_delete', 'forget', 'reset', 'channel'])
async def test_cleanup_during_receipt_cancels_pending_without_reinsertion(store, cleanup):
    from types import SimpleNamespace
    store.cases_per_tenant = 1
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    client = create_client(store)
    losing = interaction()
    losing.response.is_done = lambda: True

    async def clean():
        command = client.tree.get_command(cleanup).callback
        kwargs: dict = {'confirm': True}
        if cleanup == 'forget':
            kwargs['case_id'] = 'all'
        elif cleanup == 'reset':
            kwargs = {}
        elif cleanup == 'channel':
            kwargs = {'enabled': False, 'confirm_purge': True}
        await command(interaction(admin=True), **kwargs)
        return SimpleNamespace(id=501)

    losing.original_response.side_effect = clean
    await client.tree.get_command('ask').callback(losing, question='must not resurrect')
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 0
    assert store.history(scope) == []
    assert not store._pending
    losing.edit_original_response.assert_not_awaited()
    store.configure(scope, True)
    fresh = interaction()
    await client.tree.get_command('ask').callback(fresh, question='fresh')
    fresh.edit_original_response.assert_awaited_once()
    await client.close()


async def test_resolution_at_capacity_and_reset_does_not_free_case_slot(store):
    store.cases_per_tenant = 1
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    case = store.candidate(scope, 'existing', 500)
    client = create_client(store)
    resolved = interaction()
    await client.tree.get_command('resolved').callback(resolved, case_id=str(case), solution='solution')
    resolved.edit_original_response.assert_awaited_once()
    assert len(store.knowledge(scope)) == 1
    await client.tree.get_command('reset').callback(interaction())
    denied = interaction()
    await client.tree.get_command('ask').callback(denied, question='still full')
    denied.original_response.assert_not_awaited()
    assert store.history(scope) == []
    assert not store._pending
    await client.close()
