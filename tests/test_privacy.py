import pytest
from helperbot.core import Store, Scope, Denied


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / 'state.db')
    for guild, channel in [(1,10), (1,11), (2,10)]:
        s.configure(Scope(guild, channel, channel, 100, admin=True), True)
    yield s
    s.close()


def test_conversation_history_is_user_thread_and_tenant_isolated_and_bounded(store):
    assert hasattr(store, 'history'), 'conversation storage missing'
    s = Scope(1,10,12,100)
    for n in range(12):
        store.candidate(s, f'question {n}', 500+n)
    assert store.history(s) == [f'question {n}' for n in range(4,12)]
    for other in [Scope(1,10,13,100), Scope(1,10,12,200), Scope(2,10,12,100), Scope(1,11,12,100)]:
        assert store.history(other) == []
    store.reset(s)
    assert store.history(s) == []


def test_admin_forget_checks_tenant_and_removes_case(store):
    assert hasattr(store, 'forget'), 'privacy deletion missing'
    a = Scope(1,10,10,100)
    case = store.candidate(a, 'private', 501)
    store.resolve(a, case, 'fixed', 502)
    with pytest.raises(Denied):
        store.forget(a, case)
    with pytest.raises(Denied):
        store.forget(Scope(2,10,10,100,admin=True), case)
    store.forget(Scope(1,10,10,100,admin=True), case)
    assert store.knowledge(a) == []
    assert store.history(a) == []


def test_user_privacy_delete_covers_authored_and_confirmed_data_in_current_guild(store):
    assert hasattr(store, 'delete_user'), 'user privacy missing'
    other_guild = store.candidate(Scope(2,10,10,100), 'other guild', 501)
    for channel in [10,11]:
        store.candidate(Scope(1,channel,channel,100), 'mine', 501)
        case = store.candidate(Scope(1,channel,channel,200), 'their question', 502)
        store.resolve(Scope(1,channel,channel,100,moderator=True), case, 'my snippet', 503)
    store.delete_user(Scope(1,10,10,100))
    assert store.db.execute('SELECT count(*) FROM cases WHERE guild=1').fetchone()[0] == 0
    assert store.db.execute('SELECT id FROM cases WHERE guild=2').fetchone()[0] == other_guild
    assert store.history(Scope(1,11,11,100)) == []


def test_disable_channel_purges_data_and_reset_keeps_confirmed_cases(store):
    assert hasattr(store, 'reset'), 'reset missing'
    s = Scope(1,10,10,100,admin=True)
    case = store.candidate(s, 'question', 501)
    store.resolve(s, case, 'solution', 502)
    store.reset(s)
    assert len(store.knowledge(s)) == 1
    store.configure(s, False)
    store.configure(s, True)
    assert store.knowledge(s) == []
    assert store.history(s) == []
