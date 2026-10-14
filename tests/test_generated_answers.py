"""Persistent candidate answers using deterministic fixtures, never live AI."""
from dataclasses import replace
import sqlite3


# Exact pre-generated-answer shape; populated legacy files must not be rebuilt.
LEGACY = """
CREATE TABLE channels (guild INTEGER, channel INTEGER, PRIMARY KEY(guild, channel));
CREATE TABLE cases (
 id INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER NOT NULL, channel INTEGER NOT NULL,
 source_channel INTEGER NOT NULL, author INTEGER NOT NULL, question TEXT NOT NULL,
 question_message INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'candidate'
 CHECK(status IN ('candidate','confirmed')), solution TEXT, resolver INTEGER,
 resolution_channel INTEGER, resolution_message INTEGER);
CREATE TABLE turns (id INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER, channel INTEGER,
 conversation INTEGER, user INTEGER, question TEXT);
INSERT INTO channels VALUES (1,10);
INSERT INTO cases VALUES (41,1,10,12,100,'old candidate',501,'candidate',NULL,NULL,NULL,NULL);
INSERT INTO cases VALUES (42,1,10,12,100,'old confirmed',502,'confirmed','human solution',100,12,503);
INSERT INTO turns VALUES (7,1,10,12,100,'old candidate');
"""

import pytest

from helperbot.core import Denied, Scope, Store
from helperbot.provider import ProviderReply, DisabledCodex
from helperbot.service import Service


SCOPE = Scope(1, 10, 12, 100, admin=True)
TEXT = 'Synthetic capacitor answer — NOT live AI'


class FixtureProvider:
    def __init__(self):
        self.requests = []

    async def answer(self, request):
        self.requests.append(request)
        return ProviderReply(TEXT, tuple(row['id'] for row in request.evidence))


async def test_service_persists_unconfirmed_answer_then_manual_resolution_retrieval_and_purge(tmp_path):
    path = tmp_path / 'state.db'
    store = Store(path)
    store.configure(SCOPE, True)
    provider = FixtureProvider()
    result = await Service(store, provider).ask(SCOPE, 'capacitor question', 501)
    assert provider.requests[0].evidence == ()
    assert TEXT in result.text
    assert store.generated_answer(SCOPE, result.case) == TEXT
    row = store.db.execute('SELECT * FROM cases WHERE id=?', (result.case,)).fetchone()
    assert row['status'] == 'candidate' and row['solution'] is None
    assert store.search_knowledge(SCOPE, 'capacitor') == []
    store.close()

    store = Store(path)
    assert store.generated_answer(SCOPE, result.case) == TEXT
    store.resolve(SCOPE, result.case, 'Human verified capacitor replacement', 502)
    second = await Service(store, provider).ask(replace(SCOPE, user=200), 'capacitor', 503)
    assert [row['id'] for row in second.evidence] == [result.case]
    assert provider.requests[-1].evidence[0]['solution'] == 'Human verified capacitor replacement'
    assert 'generated_answer' not in provider.requests[-1].evidence[0]
    store.delete_user(SCOPE)
    store.close()

    store = Store(path)
    assert store.search_knowledge(SCOPE, 'capacitor') == []
    assert store.db.execute('SELECT count(*) FROM generated_answers WHERE case_id=?', (result.case,)).fetchone()[0] == 0
    # An answer derived from deleted evidence must not retain that evidence's text.
    assert store.generated_answer(replace(SCOPE, user=200), second.case) is None
    store.close()


def test_legacy_migration_is_versioned_idempotent_and_non_destructive(tmp_path):
    path = tmp_path / 'legacy.db'
    db = sqlite3.connect(path)
    db.executescript(LEGACY)
    before = {table: db.execute(f'SELECT * FROM {table}').fetchall()
              for table in ('channels', 'cases', 'turns', 'sqlite_sequence')}
    db.close()
    for _ in range(2):
        store = Store(path)
        assert store.db.execute('PRAGMA user_version').fetchone()[0] == 1
        for table, rows in before.items():
            assert [tuple(row) for row in store.db.execute(f'SELECT * FROM {table}')] == rows
        assert store.generated_answer(SCOPE, 41) is None
        assert store.generated_answer(SCOPE, 42) is None
        assert store.db.execute('PRAGMA foreign_key_check').fetchall() == []
        store.close()
    store = Store(path)
    assert store.candidate(SCOPE, 'new candidate', 600) == 43
    store.close()


def test_future_schema_is_rejected_without_writes(tmp_path):
    path = tmp_path / 'future.db'
    db = sqlite3.connect(path)
    db.executescript(LEGACY + 'PRAGMA user_version=99;')
    before = list(db.iterdump())
    db.close()
    with pytest.raises(Denied, match='schema'):
        Store(path)
    db = sqlite3.connect(path)
    assert list(db.iterdump()) == before
    assert db.execute('PRAGMA user_version').fetchone()[0] == 99
    db.close()
