"""Boundary and failure tests for synthetic generated drafts."""
import asyncio
import sqlite3
from dataclasses import replace

import pytest

from helperbot.core import Denied, Scope, Store
from helperbot.provider import DisabledCodex, ProviderReply
from helperbot.service import Service
from test_generated_answers import SCOPE, TEXT, FixtureProvider, LEGACY


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / 'state.db')
    value.configure(SCOPE, True)
    yield value
    value.close()


@pytest.mark.parametrize('text', ['x' * 1001, ' ' * 1000 + 'x', '\x00secret', '  ', '', None])
async def test_invalid_generated_text_is_never_saved(store, text):
    class InvalidFixture:
        async def answer(self, request):
            return ProviderReply(text, ())
    result = await Service(store, InvalidFixture()).ask(SCOPE, 'question', 501)
    assert store.generated_answer(SCOPE, result.case) is None
    assert '생성 답변 없음' in result.text


@pytest.mark.parametrize('citations', [(True,), (1.0,), (1, 1), (999,), '1'])
async def test_invalid_citations_never_save_an_answer(store, citations):
    source = store.candidate(SCOPE, 'question', 500)
    assert source == 1
    store.resolve(SCOPE, source, 'human solution', 502)
    class InvalidFixture:
        async def answer(self, request):
            return ProviderReply(TEXT, citations)
    result = await Service(store, InvalidFixture()).ask(SCOPE, 'question', 503)
    assert store.generated_answer(SCOPE, result.case) is None


async def test_exact_unicode_bound_and_single_answer_per_candidate(store):
    class MaxFixture:
        async def answer(self, request):
            return ProviderReply('😀' * 1000, ())
    result = await Service(store, MaxFixture()).ask(SCOPE, 'question', 501)
    assert store.generated_answer(SCOPE, result.case) == '😀' * 1000
    with store.operation(SCOPE) as pending:
        with pytest.raises(sqlite3.IntegrityError):
            store.save_generated_answer(SCOPE, result.case, 'overwrite', pending)
    assert store.generated_answer(SCOPE, result.case) == '😀' * 1000


@pytest.mark.parametrize('changes', [dict(guild=2), dict(channel=20), dict(conversation=13),
                                    dict(user=200), dict(user=200, moderator=True), dict(bot=True)])
def test_draft_access_and_save_are_owner_tenant_conversation_scoped(store, changes):
    case = store.candidate(SCOPE, 'question', 501)
    other = replace(SCOPE, **changes)
    if not other.bot:
        store.configure(other, True)
    with pytest.raises(Denied):
        store.generated_answer(other, case)
    with store.operation(other) as pending:
        with pytest.raises(Denied):
            store.save_generated_answer(other, case, TEXT, pending)
    assert store.generated_answer(SCOPE, case) is None


def test_guard_requires_active_matching_uncancelled_operation(store):
    case = store.candidate(SCOPE, 'question', 501)
    with store.operation(SCOPE) as pending:
        with pytest.raises(Denied):
            store.save_generated_answer(replace(SCOPE, user=200), case, TEXT, pending)
        store.reset(SCOPE)
        with pytest.raises(Denied):
            store.save_generated_answer(SCOPE, case, TEXT, pending)
    with pytest.raises(Denied):
        store.save_generated_answer(SCOPE, case, TEXT, pending)
    assert store.generated_answer(SCOPE, case) is None


@pytest.mark.parametrize('evidence', [(999,), (True,), tuple(range(1, 5))])
def test_bad_evidence_rolls_back_generated_answer(store, evidence):
    source = store.candidate(SCOPE, 'source', 500)
    store.resolve(SCOPE, source, 'human', 502)
    case = store.candidate(SCOPE, 'question', 501)
    with store.operation(SCOPE) as pending:
        with pytest.raises(Denied):
            store.save_generated_answer(SCOPE, case, TEXT, pending, evidence)
    assert store.generated_answer(SCOPE, case) is None
    assert store.db.execute('SELECT count(*) FROM generated_answer_sources').fetchone()[0] == 0


@pytest.mark.parametrize('answer', ['x' * 1001, 'x\x00' + 'y' * 10000, '\x00', ' '])
def test_direct_store_rejects_invalid_drafts(store, answer):
    case = store.candidate(SCOPE, 'question', 501)
    with store.operation(SCOPE) as pending:
        with pytest.raises(Denied):
            store.save_generated_answer(SCOPE, case, answer, pending)
    assert store.generated_answer(SCOPE, case) is None


def test_database_constraint_rejects_embedded_nul_size_bypass(store):
    case = store.candidate(SCOPE, 'question', 501)
    with store.db, pytest.raises(sqlite3.IntegrityError):
        store.db.execute('INSERT INTO generated_answers VALUES (?,?)', (case, 'x\x00' + 'y' * 10000))
    assert store.generated_answer(SCOPE, case) is None


def test_evidence_links_are_bounded_even_when_all_sources_exist(store):
    sources = []
    for i in range(4):
        source = store.candidate(SCOPE, 'source', 600 + i)
        store.resolve(SCOPE, source, 'human', 700 + i)
        sources.append(source)
    case = store.candidate(SCOPE, 'question', 501)
    with store.operation(SCOPE) as pending:
        with pytest.raises(Denied):
            store.save_generated_answer(SCOPE, case, TEXT, pending, tuple(sources))
    assert store.generated_answer(SCOPE, case) is None


async def test_storage_failure_is_not_disguised_as_provider_success(store):
    store.db.execute("""CREATE TRIGGER reject_answer AFTER INSERT ON generated_answers
        BEGIN SELECT RAISE(ABORT, 'synthetic insert failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        await Service(store, FixtureProvider()).ask(SCOPE, 'question', 501)
    assert not store._pending
    assert store.db.execute('SELECT count(*) FROM generated_answers').fetchone()[0] == 0
    assert store.db.execute('SELECT status FROM cases').fetchone()[0] == 'candidate'
    assert store.history(SCOPE) == ['question']  # earlier explicit submission is retained


def test_atomic_answer_and_sources_rollback_after_partial_insert(store):
    source = store.candidate(SCOPE, 'source', 500)
    store.resolve(SCOPE, source, 'human', 502)
    case = store.candidate(SCOPE, 'question', 501)
    store.db.execute("""CREATE TRIGGER reject_source AFTER INSERT ON generated_answer_sources
        BEGIN SELECT RAISE(ABORT, 'synthetic source failure'); END""")
    with store.operation(SCOPE) as pending:
        with pytest.raises(sqlite3.IntegrityError):
            store.save_generated_answer(SCOPE, case, TEXT, pending, (source,))
    assert store.generated_answer(SCOPE, case) is None
    assert store.db.execute('SELECT count(*) FROM generated_answer_sources').fetchone()[0] == 0


def test_migration_failure_rolls_back_ddl_version_and_closes_connection(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    original = sqlite3.connect
    db = original(path)
    db.executescript(LEGACY)
    before = list(db.iterdump())
    db.close()
    connections = []
    def failing_connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connections.append(connection)
        connection.set_authorizer(lambda action, name, *rest:
            sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE
            and name == 'generated_answer_sources' else sqlite3.SQLITE_OK)
        return connection
    monkeypatch.setattr(sqlite3, 'connect', failing_connect)
    with pytest.raises(sqlite3.DatabaseError):
        Store(path)
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute('SELECT 1')
    db = original(path)
    assert list(db.iterdump()) == before
    assert db.execute('PRAGMA user_version').fetchone()[0] == 0
    db.close()


def test_save_does_not_overwrite_concurrent_human_confirmation(store):
    case = store.candidate(SCOPE, 'question', 501)
    with store.operation(SCOPE) as pending:
        store.resolve(SCOPE, case, 'human authoritative summary', 502)
        with pytest.raises(Denied):
            store.save_generated_answer(SCOPE, case, TEXT, pending)
    assert store.generated_answer(SCOPE, case) is None
    assert store.knowledge(SCOPE)[0]['solution'] == 'human authoritative summary'


async def test_privacy_failure_rolls_back_cascades_and_source_links(store):
    source = await Service(store, FixtureProvider()).ask(SCOPE, 'capacitor', 500)
    store.resolve(SCOPE, source.case, 'human capacitor fix', 502)
    other = replace(SCOPE, user=200)
    derived = await Service(store, FixtureProvider()).ask(other, 'capacitor', 501)
    store.db.execute("""CREATE TRIGGER reject_purge AFTER DELETE ON cases
        BEGIN SELECT RAISE(ABORT, 'synthetic purge failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.delete_user(SCOPE)
    assert store.generated_answer(SCOPE, source.case) == TEXT
    assert store.generated_answer(other, derived.case) == TEXT
    assert store.db.execute('SELECT count(*) FROM generated_answer_sources').fetchone()[0] == 1
    assert store.db.execute('PRAGMA foreign_key_check').fetchall() == []


async def test_generated_storage_uses_existing_capacity_without_eviction(tmp_path, monkeypatch):
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '2')
    path = tmp_path / 'state.db'
    store = Store(path)
    store.configure(SCOPE, True)
    first = await Service(store, FixtureProvider()).ask(SCOPE, 'question', 501)
    second = await Service(store, FixtureProvider()).ask(SCOPE, 'question', 502)
    assert store.generated_answer(SCOPE, second.case) == TEXT
    with pytest.raises(Denied):
        await Service(store, FixtureProvider()).ask(SCOPE, 'question', 503)
    store.close()
    monkeypatch.setenv('HELPER_CASES_PER_TENANT', '1')
    store = Store(path)
    assert store.generated_answer(SCOPE, first.case) == TEXT
    assert store.generated_answer(SCOPE, second.case) == TEXT
    store.resolve(SCOPE, first.case, 'human solution at full capacity', 504)
    assert len(store.knowledge(SCOPE)) == 1
    store.close()


async def test_disabled_and_provider_timeout_never_persist_fallback(store):
    result = await Service(store, DisabledCodex()).ask(SCOPE, 'question', 501)
    assert store.generated_answer(SCOPE, result.case) is None
    class WaitingFixture:
        async def answer(self, request):
            await asyncio.Event().wait()
    result = await Service(store, WaitingFixture(), timeout=0.01).ask(SCOPE, 'question', 502)
    assert store.generated_answer(SCOPE, result.case) is None
    assert not store._pending
