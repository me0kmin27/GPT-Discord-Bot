"""Public /ask path uses ranked evidence; replace Discord HTTP only."""
import pytest

from helperbot.core import Scope
from helperbot.discord_app import create_client
from test_discord import interaction, store


@pytest.mark.parametrize('query', ['프린터 연결', 'unicorn'])
async def test_public_ask_retrieval_keeps_receipts_and_honest_no_match(store, query):
    owner = Scope(1, 10, 13, 200, admin=True)
    store.configure(owner, True)
    relevant = store.candidate(owner, '프린터가 연결되지 않습니다', 600)
    store.resolve(owner, relevant, 'USB 케이블을 교체했습니다', 601)
    for _ in range(4):
        other = store.candidate(owner, 'garden watering', 700)
        store.resolve(owner, other, 'Use rainwater', 701)
    client = create_client(store)
    try:
        i = interaction(thread=True, channel=12)
        await client.tree.get_command('ask').callback(i, question=query)
        text = i.edit_original_response.call_args.kwargs['content']
        assert '생성 답변이 아닙니다' in text
        assert 'Codex 실시간 생성 비활성' in text
        assert 'rainwater' not in text
        if query == 'unicorn':
            assert '일치하는 확정 사례를 찾지 못했습니다' in text
            assert '/1/13/601' not in text
        else:
            assert 'USB 케이블' in text
            assert 'https://discord.com/channels/1/13/601' in text
        row = store.db.execute('SELECT * FROM cases ORDER BY id DESC LIMIT 1').fetchone()
        assert row['question'] == query
        assert row['status'] == 'candidate'
        assert row['question_message'] == 501
        assert not store._pending
    finally:
        await client.close()
