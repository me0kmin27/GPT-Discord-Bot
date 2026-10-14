"""Real Service/stdio/SQLite/manual commands. All generated text is a fixture."""
from pathlib import Path
import sys

from helperbot import codex_transport as transport
from helperbot.core import Store
from helperbot.discord_app import create_client
from helperbot.service import Service
from test_discord import interaction
from test_generated_answers import SCOPE, TEXT


async def test_stdio_candidate_restart_manual_resolved_retrieval_privacy_and_reopen(tmp_path, monkeypatch):
    # Only the executable is a fixture; public answer() and storage are real.
    fixture = Path(__file__).with_name('generated_answer_protocol_fixture.py')
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command', lambda self: (sys.executable, str(fixture)))
    class RecordingTransport(transport.CodexOAuthProvider):
        def __init__(self):
            super().__init__(Path(sys.executable), tmp_path / 'provider')
            self.requests = []

        async def answer(self, request):
            self.requests.append(request)
            return await super().answer(request)

    provider = RecordingTransport()
    path = tmp_path / 'state.db'
    store = Store(path)
    store.configure(SCOPE, True)
    result = await Service(store, provider).ask(SCOPE, 'capacitor question', 501)
    assert provider.requests[0].evidence == ()
    assert TEXT in result.text
    assert store.generated_answer(SCOPE, result.case) == TEXT
    assert store.knowledge(SCOPE) == []
    store.close()

    store = Store(path)
    assert store.generated_answer(SCOPE, result.case) == TEXT
    client = create_client(store)
    confirmation = interaction(thread=True, channel=12)
    confirmation.original_response.return_value.id = 502
    await client.tree.get_command('resolved').callback(
        confirmation, case_id=str(result.case), solution='Human tested capacitor replacement works')
    confirmation.edit_original_response.assert_awaited_once()
    second = await Service(store, provider).ask(SCOPE, 'capacitor question', 503)
    assert [row['id'] for row in provider.requests[-1].evidence] == [result.case]
    assert provider.requests[-1].evidence[0]['solution'] == 'Human tested capacitor replacement works'
    assert '/1/12/502' in second.text
    assert store.generated_answer(SCOPE, second.case) == TEXT
    await client.tree.get_command('privacy_delete').callback(interaction(), confirm=True)
    assert not store._pending
    await client.close()
    store.close()

    store = Store(path)
    for table in ('cases', 'turns', 'generated_answers', 'generated_answer_sources'):
        assert store.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
    assert store.knowledge(SCOPE) == []
    assert store.db.execute('PRAGMA foreign_key_check').fetchall() == []
    store.close()
    assert not list((tmp_path / 'provider').glob('request-*'))


async def test_selected_provider_reaches_real_ask_callback_and_persists(tmp_path, monkeypatch):
    from helperbot.provider import build_provider
    fixture = Path(__file__).with_name('generated_answer_protocol_fixture.py')
    monkeypatch.setattr(transport.CodexOAuthProvider, '_command', lambda self: (sys.executable, str(fixture)))
    provider = build_provider('codex-oauth', executable=Path(sys.executable), data=tmp_path / 'provider')
    store = Store(tmp_path / 'state.db')
    store.configure(SCOPE, True)
    client = create_client(store, provider=provider)
    receipt = interaction(thread=True, channel=12)
    receipt.original_response.return_value.id = 501
    try:
        await client.tree.get_command('ask').callback(receipt, question='capacitor question')
        receipt.edit_original_response.assert_awaited_once()
        assert TEXT in receipt.edit_original_response.call_args.kwargs['content']
        row = store.db.execute('SELECT id FROM cases').fetchone()
        assert store.generated_answer(SCOPE, row[0]) == TEXT
        assert store.knowledge(SCOPE) == []
    finally:
        await client.close()
        store.close()
