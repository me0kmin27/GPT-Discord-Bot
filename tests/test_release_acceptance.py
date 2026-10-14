"""Offline release scenario: real Service/Store/SQLite, synthetic receipt IDs.

No Discord client, HTTP mock, credentials, model response, or live claim.
"""
from helperbot.core import Scope, Store
from helperbot.provider import DisabledCodex
from helperbot.service import Service


async def test_question_confirm_retrieve_privacy_delete_persists(tmp_path, monkeypatch):
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '1000')
    path = tmp_path / 'acceptance.db'
    owner = Scope(1, 10, 12, 100, admin=True)
    reader = Scope(1, 10, 14, 200)
    unrelated = Scope(1, 10, 14, 300)
    other = Scope(2, 10, 12, 100, admin=True)
    store = Store(path)
    try:
        assert store.knowledge(owner) == []
        store.configure(owner, True)
        store.configure(other, True)
        service = Service(store, DisabledCodex())
        question = await service.ask(owner, '프린터 연결 오류', 501)
        assert question.evidence == ()
        assert '비활성' in question.text
        assert store.search_knowledge(reader, '프린터 연결') == []
        assert store.db.execute('SELECT status FROM cases WHERE id=?',
                                (question.case,)).fetchone()[0] == 'candidate'
        store.resolve(owner, question.case, 'USB 케이블 교체', 502)

        # Newer unrelated confirmed knowledge must not replace relevant evidence.
        noise = await service.ask(unrelated, '정원 물주기', 601)
        store.resolve(unrelated, noise.case, '빗물 사용', 602)
        foreign = await service.ask(other, '프린터 연결 오류', 701)
        store.resolve(other, foreign.case, '다른 서버 전용 해결', 702)
        retrieved = await service.ask(reader, '프린터 연결', 503)
        assert [item['id'] for item in retrieved.evidence] == [question.case]
        assert 'USB 케이블 교체' in retrieved.text
        assert 'https://discord.com/channels/1/12/502' in retrieved.text
        assert '생성 답변이 아닙니다' in retrieved.text
        assert '다른 서버 전용 해결' not in retrieved.text
        assert len(store.knowledge(owner)) == 2  # ask never confirms its output

        # Same operation as /privacy_delete; only this guild's owner data removed.
        store.delete_user(owner)
        assert store.history(owner) == []
        assert store.db.execute('SELECT id FROM cases WHERE id=?',
                                (question.case,)).fetchone() is None
        after = await service.ask(reader, '프린터 연결', 504)
        assert after.evidence == ()
        assert '일치하는 확정 사례를 찾지 못했습니다' in after.text
        assert 'USB 케이블 교체' not in after.text
        assert '/1/12/502' not in after.text
        assert [r['id'] for r in store.knowledge(unrelated)] == [noise.case]
        assert [r['id'] for r in store.knowledge(other)] == [foreign.case]
    finally:
        store.close()

    # Reopen the actual file: deletion and unaffected tenant data are durable.
    reopened = Store(path)
    try:
        assert reopened.history(owner) == []
        assert reopened.search_knowledge(reader, '프린터 연결') == []
        assert reopened.db.execute('SELECT id FROM cases WHERE id=?',
                                   (question.case,)).fetchone() is None
        assert [r['id'] for r in reopened.knowledge(other)] == [foreign.case]
    finally:
        reopened.close()
