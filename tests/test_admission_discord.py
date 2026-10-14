"""Real command callbacks / SQLite; only Discord HTTP is replaced."""
import asyncio
import pytest
from helperbot.core import Scope
from helperbot.discord_app import create_client
from test_discord import interaction, store


@pytest.mark.parametrize('command', ['ask', 'resolved'])
async def test_admission_before_public_receipt_and_write(store, command, monkeypatch, caplog):
    monkeypatch.setenv('HELPER_ADMISSION_USER_REQUESTS', '1')
    client = create_client(store)
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    first = interaction()
    await client.tree.get_command('ask').callback(first, question='first')
    case = store.db.execute('SELECT id FROM cases').fetchone()[0]
    denied = interaction(thread=True, channel=12)
    kwargs = {'question': 'sensitive denied question'} if command == 'ask' else {
        'case_id': str(case), 'solution': 'sensitive denied solution'}
    await client.tree.get_command(command).callback(denied, **kwargs)
    assert denied.response.send_message.call_args.kwargs.get('ephemeral') is True
    assert 'embed' not in denied.response.send_message.call_args.kwargs
    denied.original_response.assert_not_awaited()
    denied.edit_original_response.assert_not_awaited()
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 1
    assert store.knowledge(scope) == []
    assert store.history(scope) == ['first']
    assert 'sensitive' not in caplog.text
    # Privacy/admin commands remain available while admission is exhausted.
    await client.tree.get_command('privacy_delete').callback(interaction(), confirm=True)
    assert store.history(scope) == []
    assert not store._pending
    await client.close()


async def test_one_user_cannot_overlap_receipts_but_other_guild_can(store):
    client = create_client(store)
    for guild in (1, 2):
        store.configure(Scope(guild, 10, 10, 100, admin=True), True)
    entered, release = asyncio.Event(), asyncio.Event()
    first = interaction()

    async def hold_receipt(*args, **kwargs):
        entered.set()
        await release.wait()

    first.response.send_message.side_effect = hold_receipt
    task = asyncio.create_task(client.tree.get_command('ask').callback(first, question='held'))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        denied = interaction(thread=True, channel=12)
        await client.tree.get_command('ask').callback(denied, question='overlap')
        assert denied.response.send_message.call_args.kwargs.get('ephemeral') is True
        denied.original_response.assert_not_awaited()
        other = interaction(guild=2)
        await client.tree.get_command('ask').callback(other, question='other guild')
        other.edit_original_response.assert_awaited_once()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await client.close()


@pytest.mark.parametrize('command', ['ask', 'resolved'])
@pytest.mark.parametrize('boundary', ['send_message', 'original_response', 'edit_original_response'])
@pytest.mark.parametrize('cancel', [False, True])
async def test_all_http_exit_paths_release_admission(store, command, boundary, cancel):
    client = create_client(store)
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    case = store.candidate(scope, 'question', 500)
    failing = interaction()
    target = failing.response if boundary == 'send_message' else failing
    error = asyncio.CancelledError if cancel else RuntimeError
    getattr(target, boundary).side_effect = error('synthetic failure')
    kwargs = {'question': 'question'} if command == 'ask' else {
        'case_id': str(case), 'solution': 'solution'}
    with pytest.raises(error):
        await client.tree.get_command(command).callback(failing, **kwargs)
    fresh = interaction()
    await client.tree.get_command('ask').callback(fresh, question='fresh')
    fresh.edit_original_response.assert_awaited_once()
    assert not store._pending
    await client.close()


@pytest.mark.parametrize('outcome', ['cancel', 'timeout', 'error', 'privacy'])
async def test_provider_exit_releases_admission_without_refunding_rate(store, monkeypatch, outcome):
    from helperbot.provider import DisabledCodex
    from helperbot.service import Service
    entered, release = asyncio.Event(), asyncio.Event()

    class GatedProvider(DisabledCodex):
        async def answer(self, request):
            entered.set()
            if outcome == 'error':
                raise RuntimeError('synthetic secret')
            await release.wait()
            return await super().answer(request)

    monkeypatch.setattr('helperbot.discord_app.DisabledCodex', GatedProvider)
    if outcome == 'timeout':
        monkeypatch.setattr('helperbot.discord_app.Service',
                            lambda store, provider: Service(store, provider, timeout=0.01))
    monkeypatch.setenv('HELPER_ADMISSION_USER_REQUESTS', '2')
    client = create_client(store)
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    task = asyncio.create_task(client.tree.get_command('ask').callback(interaction(), question='first'))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if outcome == 'cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            if outcome == 'privacy':
                store.delete_user(scope)
                release.set()
            await asyncio.wait_for(task, 2)
        release.set()
        fresh = interaction()
        await client.tree.get_command('ask').callback(fresh, question='second')
        fresh.edit_original_response.assert_awaited_once()
        denied = interaction()
        await client.tree.get_command('ask').callback(denied, question='third')
        assert denied.response.send_message.call_args.kwargs.get('ephemeral') is True
        denied.original_response.assert_not_awaited()
        assert not store._pending
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await client.close()


async def test_invalid_input_and_permissions_do_not_consume_budget(store, monkeypatch):
    monkeypatch.setenv('HELPER_ADMISSION_USER_REQUESTS', '1')
    client = create_client(store)
    # Disabled channel then invalid content and unauthorized resolution.
    await client.tree.get_command('ask').callback(interaction(), question='disabled')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    await client.tree.get_command('ask').callback(interaction(), question=' ')
    case = store.candidate(Scope(1, 10, 10, 200), 'other author', 500)
    await client.tree.get_command('resolved').callback(interaction(), case_id=str(case), solution='not allowed')
    valid = interaction()
    await client.tree.get_command('ask').callback(valid, question='valid')
    valid.edit_original_response.assert_awaited_once()
    await client.close()
