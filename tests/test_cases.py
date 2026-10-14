import pytest
from helperbot.core import Store, Scope, Denied


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / 'state.db')
    s.configure(Scope(1, 10, 10, 100, admin=True), True)
    yield s
    s.close()


def test_explicit_question_stays_candidate_until_author_confirms(store):
    author = Scope(1, 10, 12, 100)
    assert hasattr(store, 'candidate'), 'candidate workflow missing'
    case = store.candidate(author, '장치가 켜지지 않아요', 501)
    assert store.knowledge(author) == []
    with pytest.raises(Denied):
        store.resolve(Scope(1, 10, 12, 200), case, '전원 교체', 502)
    store.resolve(author, case, '전원 케이블을 교체하여 해결했습니다.', 503)
    items = store.knowledge(Scope(1, 10, 14, 200))
    assert len(items) == 1
    assert items[0]['status'] == 'confirmed'
    assert items[0]['question_message'] == 501
    assert items[0]['resolution_message'] == 503
    assert items[0]['source_channel'] == 12
    assert items[0]['solution'].startswith('전원')
    assert store.knowledge(Scope(2, 10, 12, 100)) == []
    assert store.knowledge(Scope(1, 11, 12, 100)) == []


def test_scope_and_bot_checks_on_all_case_writes(store):
    assert hasattr(store, 'candidate'), 'candidate workflow missing'
    for invalid in [Scope(0, 10, 10, 100), Scope(1, 11, 11, 100), Scope(1, 10, 10, 100, bot=True)]:
        with pytest.raises(Denied):
            store.candidate(invalid, 'question', 501)
    case = store.candidate(Scope(1, 10, 10, 100), 'question', 501)
    for invalid in [Scope(2, 10, 10, 100, moderator=True), Scope(1, 11, 11, 100, moderator=True), Scope(1, 10, 10, 100, bot=True)]:
        with pytest.raises(Denied):
            store.resolve(invalid, case, 'solution', 502)
    store.resolve(Scope(1, 10, 10, 200, moderator=True), case, 'verified solution', 502)
    with pytest.raises(Denied):
        store.resolve(Scope(1, 10, 10, 100), case, 'overwrite', 503)


@pytest.mark.parametrize('text', ['', '  ', 'x' * 2001])
def test_candidate_rejects_empty_or_unbounded_input(store, text):
    assert hasattr(store, 'candidate'), 'candidate workflow missing'
    with pytest.raises(Denied):
        store.candidate(Scope(1, 10, 10, 100), text, 501)
