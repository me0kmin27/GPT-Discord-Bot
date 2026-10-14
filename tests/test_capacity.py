"""Stored-case quota counts candidates and confirmed rows together."""
import pytest
from helperbot.core import Denied, Scope, Store


def test_total_capacity_rejects_without_writing_history(tmp_path, monkeypatch):
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '2')
    store = Store(tmp_path / 'state.db')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    first = store.candidate(scope, 'first', 501)
    store.resolve(scope, first, 'solution', 601)
    store.candidate(scope, 'second', 502)
    with pytest.raises(Denied, match='저장 한도'):
        store.candidate(scope, 'overflow', 503)
    assert store.history(scope) == ['first', 'second']
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 2
    assert len(store.knowledge(scope)) == 1
    store.close()


@pytest.mark.parametrize('raw', ['', '0', '-1', '100001', '1.5', ' 2', '+2', '１２', 'private-invalid-value'])
def test_invalid_limit_fails_before_creating_database(tmp_path, monkeypatch, raw):
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', raw)
    path = tmp_path / 'state.db'
    with pytest.raises(ValueError, match='^Invalid case capacity configuration$'):
        Store(path)
    assert not path.exists()


@pytest.mark.parametrize('raw', ['1', '100000'])
def test_valid_limit_edges(tmp_path, monkeypatch, raw):
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', raw)
    store = Store(tmp_path / 'state.db')
    assert store.cases_per_tenant == int(raw)
    store.close()


def test_tenant_is_guild_and_parent_channel(tmp_path, monkeypatch):
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '1')
    store = Store(tmp_path / 'state.db')
    parent = Scope(1, 10, 10, 100, admin=True)
    store.configure(parent, True)
    store.candidate(parent, 'parent', 501)
    for conversation in (10, 11, 12):
        with pytest.raises(Denied):
            store.candidate(Scope(1, 10, conversation, 200), 'shared', 502)
    for guild, channel in ((2, 10), (1, 20)):
        other = Scope(guild, channel, channel, 100, admin=True)
        store.configure(other, True)
        store.candidate(other, 'isolated', 503)
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 3
    store.close()


def test_lowering_limit_preserves_rows_and_allows_resolution_and_cleanup(tmp_path, monkeypatch):
    path = tmp_path / 'state.db'
    scope = Scope(1, 10, 10, 100, admin=True)
    store = Store(path)
    store.configure(scope, True)
    ids = [store.candidate(scope, f'question {n}', 500 + n) for n in range(3)]
    store.close()
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '1')
    store = Store(path)
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 3
    store.resolve(scope, ids[0], 'still allowed', 600)
    with pytest.raises(Denied):
        store.candidate(scope, 'denied', 504)
    store.forget(scope, ids[1])
    store.forget(scope, ids[2])
    with pytest.raises(Denied):
        store.candidate(scope, 'still full', 505)
    store.delete_user(scope)
    store.candidate(scope, 'now fits', 506)
    store.close()


@pytest.mark.parametrize('cleanup', ['forget', 'privacy', 'source', 'channel', 'guild', 'disable'])
def test_explicit_cleanup_frees_capacity(tmp_path, monkeypatch, cleanup):
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '1')
    store = Store(tmp_path / 'state.db')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    case = store.candidate(scope, 'first', 500)
    actions = {
        'forget': lambda: store.forget(scope, case),
        'privacy': lambda: store.delete_user(scope),
        'source': lambda: store.delete_sources(1, 10, [500]),
        'channel': lambda: store.delete_channel(1, 10),
        'guild': lambda: store.delete_guild(1),
        'disable': lambda: store.configure(scope, False),
    }
    actions[cleanup]()
    store.configure(scope, True)
    store.candidate(scope, 'replacement', 501)
    assert store.history(scope) == ['replacement']
    store.close()


def test_two_connections_cannot_overfill_after_successful_preflights(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '1')
    path = tmp_path / 'state.db'
    scope = Scope(1, 10, 10, 100, admin=True)
    store = Store(path)
    store.configure(scope, True)
    ready = Barrier(2)

    def write(message):
        writer = Store(path)
        try:
            writer.check_capacity(scope)
            ready.wait(timeout=5)
            try:
                writer.candidate(scope, 'competing', message)
                return 'stored'
            except Denied:
                return 'denied'
        finally:
            writer.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, [501, 502])) == ['denied', 'stored']
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 1
    assert store.history(scope) == ['competing']
    store.close()


def test_candidate_failure_rolls_back_case_and_history(tmp_path, monkeypatch):
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '1')
    store = Store(tmp_path / 'state.db')
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    store.db.execute("CREATE TRIGGER fail_turn BEFORE INSERT ON turns BEGIN SELECT RAISE(ABORT, 'synthetic'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.candidate(scope, 'failed', 500)
    assert not store.db.in_transaction
    assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 0
    assert store.history(scope) == []
    store.db.execute('DROP TRIGGER fail_turn')
    store.candidate(scope, 'retry', 501)
    store.close()


def test_lock_failure_is_closed_and_retry_works(tmp_path, monkeypatch):
    import sqlite3
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '1')
    path = tmp_path / 'state.db'
    store = Store(path)
    scope = Scope(1, 10, 10, 100, admin=True)
    store.configure(scope, True)
    other = Store(path)
    store.db.execute('PRAGMA busy_timeout=1')
    other.db.execute('BEGIN IMMEDIATE')
    try:
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            store.candidate(scope, 'locked', 500)
        assert not store.db.in_transaction
        assert store.db.execute('SELECT count(*) FROM cases').fetchone()[0] == 0
        assert store.history(scope) == []
    finally:
        other.db.rollback()
        other.close()
    store.candidate(scope, 'retry', 501)
    store.close()


def test_default_limit(tmp_path, monkeypatch):
    monkeypatch.delenv('HELPER_CASES_PER_TENANT', raising=False)
    store = Store(tmp_path / 'state.db')
    assert store.cases_per_tenant == 1000
    store.close()
