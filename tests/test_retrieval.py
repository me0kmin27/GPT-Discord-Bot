"""Real SQLite + service retrieval regressions; no model/network calls."""
import pytest

from helperbot.core import Scope, Store
from helperbot.provider import DisabledCodex
from helperbot.service import Service


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / 'state.db')
    db.configure(Scope(1, 10, 10, 100, admin=True), True)
    yield db
    db.close()


def confirmed(store, question, solution='fixed', scope=None):
    scope = scope or Scope(1, 10, 12, 100)
    case = store.candidate(scope, question, 10000)
    store.resolve(scope, case, solution, 20000)
    return case


async def test_question_match_beats_newest_and_keeps_original_citation(store):
    relevant = confirmed(store, 'printer offline', 'Reconnect USB cable')
    for _ in range(25):
        confirmed(store, 'garden watering', 'Use rainwater')
    result = await Service(store, DisabledCodex()).ask(
        Scope(1, 10, 14, 200), 'printer offline', 30000)
    assert [item['id'] for item in result.evidence] == [relevant]
    assert 'Reconnect USB cable' in result.text
    assert 'https://discord.com/channels/1/12/20000' in result.text
    assert '관련성 미검증' not in result.text
    assert '생성 답변이 아닙니다' in result.text


@pytest.mark.parametrize(('question', 'solution', 'query'), [
    ('프린터가 연결되지 않습니다', '케이블 교체', '프린터 연결'),
    ('인쇄 실패', '드라이버를 재설치했습니다', '드라이버 재설치'),
    ('USB 연결 오류', '포트 교체', 'ｕｓｂ'),
    ('전원이 안 켜집니다', '배터리 교체', '전원'),
])
def test_korean_particles_solution_terms_and_unicode(store, question, solution, query):
    case = confirmed(store, question, solution)
    assert [r['id'] for r in store.search_knowledge(Scope(1, 10, 14, 200), query)] == [case]


@pytest.mark.parametrize('query', ['unicorn', '!!! % _ * " : ()', '😀'])
async def test_no_match_does_not_claim_no_cases_or_show_newest(store, query):
    confirmed(store, 'printer', 'Reconnect USB cable')
    result = await Service(store, DisabledCodex()).ask(Scope(1, 10, 10, 200), query, 30000)
    assert result.evidence == ()
    assert '일치하는 확정 사례를 찾지 못했습니다' in result.text
    assert '아직 확정된 사례가 없습니다' not in result.text
    assert 'Reconnect' not in result.text
    assert 'https://discord.com/channels/' not in result.text


def test_score_then_newest_id_tie_break_and_no_repetition_boost(store):
    s = Scope(1, 10, 10, 200)
    best = confirmed(store, 'printer offline', 'cable')
    repeated = confirmed(store, 'printer ' * 100, 'printer ' * 100)
    latest = confirmed(store, 'printer', 'fixed')
    for _ in range(3):
        assert [r['id'] for r in store.search_knowledge(s, 'PRINTER offline printer')] == [best, latest, repeated]
    extra = confirmed(store, 'printer', 'fixed')
    assert [r['id'] for r in store.search_knowledge(s, 'printer offline')] == [best, extra, latest]


def test_tenant_filters_precede_ranking_and_candidates_are_excluded(store):
    query = 'printer offline cable'
    s = Scope(1, 10, 14, 200)
    own = confirmed(store, 'printer', 'fixed')
    store.candidate(s, query, 30000)
    for other in [Scope(2, 10, 12, 100, admin=True), Scope(1, 20, 12, 100, admin=True)]:
        store.configure(other, True)
        confirmed(store, query, query, other)
        assert store.search_knowledge(other, query)[0]['guild'] == other.guild
    assert [r['id'] for r in store.search_knowledge(s, query)] == [own]
    for denied in [Scope(0, 10, 10, 100), Scope(1, 99, 99, 100), Scope(1, 10, 10, 100, bot=True)]:
        assert store.search_knowledge(denied, query) == []


@pytest.mark.parametrize('query', [
    "' OR 1=1 --", '"; DROP TABLE cases; --', 'printer* OR secret',
    'NEAR(secret, password)', '% _', "' UNION SELECT * FROM cases --",
])
def test_query_syntax_is_only_text_not_sql_fts_or_wildcards(store, query):
    confirmed(store, 'printers', 'fixed')
    other = Scope(2, 10, 10, 100, admin=True)
    store.configure(other, True)
    confirmed(store, query, query, other)
    before = [tuple(r) for r in store.db.execute('SELECT * FROM cases ORDER BY id')]
    assert store.search_knowledge(Scope(1, 10, 10, 100), query) == []
    assert store.search_knowledge(Scope("1 OR 1=1", 10, 10, 100), query) == []
    assert before == [tuple(r) for r in store.db.execute('SELECT * FROM cases ORDER BY id')]


@pytest.mark.parametrize('query', ['', ' ', 'x' * 2001, None])
def test_search_reuses_input_bound(store, query):
    from helperbot.core import Denied
    with pytest.raises(Denied):
        store.search_knowledge(Scope(1, 10, 10, 100), query)


def test_fixed_window_filters_before_limit_and_preserves_older_rows(tmp_path, monkeypatch):
    from helperbot.core import SEARCH_WINDOW
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '2000')
    db = Store(tmp_path / 'bounded.db')
    s = Scope(1, 10, 10, 100, admin=True)
    db.configure(s, True)
    try:
        oldest = confirmed(db, 'outsidewindow', scope=s)
        edge = confirmed(db, 'edgekeyword', scope=s)
        for _ in range(SEARCH_WINDOW - 1):
            confirmed(db, 'unrelated', scope=s)
        db.candidate(s, 'edgekeyword', 30000)
        other = Scope(2, 10, 10, 100, admin=True)
        db.configure(other, True)
        confirmed(db, 'edgekeyword', scope=other)
        assert db.search_knowledge(s, 'outsidewindow') == []
        assert [r['id'] for r in db.search_knowledge(s, 'edgekeyword')] == [edge]
        assert db.db.execute('SELECT id FROM cases WHERE id=?', (oldest,)).fetchone()
        assert len(db.search_knowledge(s, 'unrelated')) == 3
    finally:
        db.close()


@pytest.mark.parametrize('event', ['question', 'resolution', 'author', 'resolver', 'forget', 'disable', 'thread', 'channel', 'guild'])
def test_deleted_evidence_disappears_without_stale_search_index(store, event):
    owner = Scope(1, 10, 12, 100, admin=True)
    resolver = Scope(1, 10, 13, 300, moderator=True)
    reader = Scope(1, 10, 14, 200)
    case = store.candidate(owner, 'printer', 10000)
    store.resolve(resolver, case, 'cable', 20000)
    assert store.search_knowledge(reader, 'printer')[0]['id'] == case
    if event == 'question':
        store.delete_sources(1, 12, [10000])
    elif event == 'resolution':
        store.delete_sources(1, 13, [20000])
    elif event in ('author', 'resolver'):
        store.delete_user(owner if event == 'author' else resolver)
    elif event == 'forget':
        store.forget(owner, case)
    elif event == 'disable':
        store.configure(owner, False)
    elif event in ('thread', 'channel'):
        store.delete_channel(1, 12 if event == 'thread' else 10)
    else:
        store.delete_guild(1)
    assert store.search_knowledge(reader, 'printer') == []
    # Re-enabling cannot resurrect deleted material; new resolution is searchable.
    store.configure(owner, True)
    fresh = confirmed(store, 'printer', scope=owner)
    assert [r['id'] for r in store.search_knowledge(reader, 'printer')] == [fresh]
