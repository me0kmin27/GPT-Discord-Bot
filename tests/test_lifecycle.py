import pytest
from helperbot.core import Store, Scope, Denied


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / 'state.db')
    for g,c in [(1,10),(1,11),(2,10)]:
        a = Scope(g,c,c,100,admin=True)
        s.configure(a,True)
        case = s.candidate(a,'explicit question',501)
        s.resolve(a,case,'explicit solution',502)
    yield s
    s.close()


def test_source_message_deletion_only_purges_matching_guild_channel(store):
    assert hasattr(store,'delete_sources'), 'source deletion metadata hook missing'
    store.delete_sources(1,10,[502])
    assert not store.knowledge(Scope(1,10,10,100))
    assert not store.history(Scope(1,10,10,100))
    assert store.knowledge(Scope(1,11,11,100))
    assert store.knowledge(Scope(2,10,10,100))


def test_channel_removal_purges_parent_and_thread_sources_without_cross_guild_effect(store):
    assert hasattr(store,'delete_channel'), 'channel removal hook missing'
    case = store.candidate(Scope(1,10,12,100),'thread question',601)
    store.resolve(Scope(1,10,12,100),case,'thread solution',602)
    store.delete_channel(1,12)
    assert len(store.knowledge(Scope(1,10,10,100))) == 1
    store.delete_channel(1,10)
    assert not store.enabled(Scope(1,10,10,100))
    assert store.enabled(Scope(2,10,10,100))
    assert store.knowledge(Scope(1,11,11,100))


def test_guild_removal_drops_configuration_cases_and_turns(store):
    assert hasattr(store,'delete_guild'), 'guild removal hook missing'
    store.delete_guild(1)
    for table in ['channels','cases','turns']:
        assert store.db.execute(f'SELECT count(*) FROM {table} WHERE guild=1').fetchone()[0] == 0
        assert store.db.execute(f'SELECT count(*) FROM {table} WHERE guild=2').fetchone()[0] > 0
