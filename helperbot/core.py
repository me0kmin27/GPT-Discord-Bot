"""Synchronous SQLite boundary; never accepts raw channel history."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import os
import re
import unicodedata


SEARCH_WINDOW = 1000
SEARCH_RESULTS = 3


def lexical_features(text):
    """Unique words + Hangul syllable bigrams, not a morphological analyzer."""
    text = unicodedata.normalize('NFKC', text).casefold()
    features = {('word', word) for word in re.findall(r'[^\W_]+', text)}
    for run in re.findall(r'[가-힣]+', text):
        features.update(('hangul', run[i:i + 2]) for i in range(len(run) - 1))
    return features


class Denied(ValueError):
    """A safe, user-facing authorization or validation error."""


@dataclass(frozen=True)
class Scope:
    guild: int
    channel: int
    conversation: int
    user: int
    admin: bool = False
    moderator: bool = False
    bot: bool = False

    @property
    def tenant(self):
        return (self.guild, self.channel)


@dataclass(eq=False)
class PendingOperation:
    scope: Scope
    awaiting_receipt: bool
    cancelled: bool = False

    def check(self):
        if self.cancelled:
            raise Denied("처리 중 설정/삭제가 변경되어 이전 응답을 폐기했습니다. 다시 질문하세요.")


class Store:
    def __init__(self, path):
        raw = os.environ.get('HELPER_CASES_PER_TENANT', '1000')
        if (not 1 <= len(raw) <= 6 or not raw.isascii() or not raw.isdecimal()
                or not 1 <= int(raw) <= 100000):
            raise ValueError('Invalid case capacity configuration')
        self.cases_per_tenant = int(raw)
        path = Path(path).absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise Denied("심볼릭 링크 데이터베이스 경로는 허용하지 않습니다.")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA foreign_keys=ON")
        try:
            self._initialize_schema()
        except BaseException:
            self.db.close()
            raise
        self._pending = set()

    def _initialize_schema(self):
        # Version 0 is the original unversioned schema. Additive DDL only;
        # serialize concurrent openers and roll back DDL + version together.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise Denied("Unsupported database schema version")
            self.db.execute("CREATE TABLE IF NOT EXISTS channels (guild INTEGER, channel INTEGER, PRIMARY KEY(guild, channel))")
            self.db.execute("""CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild INTEGER NOT NULL, channel INTEGER NOT NULL,
                source_channel INTEGER NOT NULL, author INTEGER NOT NULL,
                question TEXT NOT NULL, question_message INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate','confirmed')),
                solution TEXT, resolver INTEGER, resolution_channel INTEGER, resolution_message INTEGER
            )""")
            self.db.execute("CREATE INDEX IF NOT EXISTS case_tenant ON cases(guild, channel, status, id)")
            self.db.execute("""CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild INTEGER, channel INTEGER,
                conversation INTEGER, user INTEGER, question TEXT
            )""")
            self.db.execute("CREATE INDEX IF NOT EXISTS turn_scope ON turns(guild, channel, conversation, user, id)")
            self.db.execute("""CREATE TABLE IF NOT EXISTS generated_answers (
                case_id INTEGER PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
                answer TEXT NOT NULL CHECK(typeof(answer)='text' AND length(answer) BETWEEN 1 AND 1000
                    AND instr(answer, char(0))=0 AND length(CAST(answer AS BLOB)) <= 4000)
            )""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS generated_answer_sources (
                answer_case INTEGER NOT NULL REFERENCES generated_answers(case_id) ON DELETE CASCADE,
                source_case INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                PRIMARY KEY(answer_case, source_case)
            )""")
            self.db.execute("CREATE INDEX IF NOT EXISTS answer_source ON generated_answer_sources(source_case)")
            self.db.execute("""CREATE TRIGGER IF NOT EXISTS purge_derived_answers BEFORE DELETE ON cases
                BEGIN
                    DELETE FROM generated_answers WHERE case_id IN (
                        SELECT answer_case FROM generated_answer_sources WHERE source_case=OLD.id);
                END""")
            self.db.execute("PRAGMA user_version=1")

    @contextmanager
    def operation(self, s, *, awaiting_receipt=False):
        # Single event-loop/process store: register before the first network await.
        # Only active operations are retained, never permanent deletion tombstones.
        operation = PendingOperation(s, awaiting_receipt)
        self._pending.add(operation)
        try:
            yield operation
        finally:
            self._pending.discard(operation)

    def _cancel(self, predicate):
        for operation in self._pending:
            if predicate(operation):
                operation.cancelled = True

    def require_enabled(self, s):
        if not s.guild or s.bot or not self.enabled(s):
            raise Denied("DM/봇 입력 또는 비활성 채널에서는 사용할 수 없습니다.")

    @staticmethod
    def text(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise Denied("내용은 공백이 아닌 1~2000자여야 합니다.")
        return value.strip()

    def check_capacity(self, s):
        self.require_enabled(s)
        count = self.db.execute(
            "SELECT count(*) FROM cases WHERE guild=? AND channel=?", s.tenant).fetchone()[0]
        if count >= self.cases_per_tenant:
            raise Denied("채널 사례 저장 한도에 도달했습니다. /privacy_delete 또는 관리자 /forget으로 삭제 후 다시 시도하세요.")

    def candidate(self, s, question, message):
        self.require_enabled(s)
        question = self.text(question)
        with self.db:
            # Serialize quota check + insert across connections. Never hold this
            # transaction across Discord/provider awaits; no automatic eviction.
            self.db.execute("BEGIN IMMEDIATE")
            self.check_capacity(s)
            cur = self.db.execute(
                "INSERT INTO cases (guild, channel, source_channel, author, question, question_message) VALUES (?,?,?,?,?,?)",
                (*s.tenant, s.conversation, s.user, question, message))
            key = (*s.tenant, s.conversation, s.user)
            self.db.execute("INSERT INTO turns(guild,channel,conversation,user,question) VALUES (?,?,?,?,?)", (*key, question))
            self.db.execute("DELETE FROM turns WHERE guild=? AND channel=? AND conversation=? AND user=? AND id NOT IN (SELECT id FROM turns WHERE guild=? AND channel=? AND conversation=? AND user=? ORDER BY id DESC LIMIT 8)", (*key, *key))
        return cur.lastrowid

    def save_generated_answer(self, s, case, answer, pending, evidence=()):
        """Attach one validated draft, never promote it or resurrect deleted cases."""
        if pending not in self._pending or pending.scope != s:
            raise Denied("유효한 요청이 아닙니다.")
        pending.check()
        answer = self.text(answer)
        if len(answer) > 1000 or '\x00' in answer:
            raise Denied("생성 답변 저장 한도를 초과했습니다.")
        if (not isinstance(evidence, (tuple, list)) or len(evidence) > SEARCH_RESULTS
                or any(type(key) is not int or not 0 < key < 2**63 for key in evidence)
                or len(set(evidence)) != len(evidence)):
            raise Denied("생성 답변의 근거가 유효하지 않습니다.")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.require_enabled(s)
            pending.check()
            row = self.db.execute(
                "SELECT id FROM cases WHERE id=? AND guild=? AND channel=? "
                "AND source_channel=? AND author=? AND status='candidate'",
                (case, *s.tenant, s.conversation, s.user)).fetchone()
            if not row:
                raise Denied("유효한 후보 사례가 아닙니다.")
            self.db.execute("INSERT INTO generated_answers(case_id,answer) VALUES (?,?)", (case, answer))
            # Track every supplied source, not merely the model's claimed citations.
            for source in evidence:
                row = self.db.execute(
                    "SELECT id FROM cases WHERE id=? AND guild=? AND channel=? AND status='confirmed'",
                    (source, *s.tenant)).fetchone()
                if not row:
                    raise Denied("생성 답변의 근거가 삭제되었거나 유효하지 않습니다.")
                self.db.execute("INSERT INTO generated_answer_sources VALUES (?,?)", (case, source))

    def generated_answer(self, s, case):
        """Owner-only draft access; drafts are not knowledge/provider evidence."""
        self.require_enabled(s)
        row = self.db.execute(
            "SELECT a.answer FROM cases c LEFT JOIN generated_answers a ON a.case_id=c.id "
            "WHERE c.id=? AND c.guild=? AND c.channel=? AND c.source_channel=? AND c.author=?",
            (case, *s.tenant, s.conversation, s.user)).fetchone()
        if not row:
            raise Denied("이 대화의 본인 사례만 조회할 수 있습니다.")
        return row['answer']

    def check_resolution(self, s, case, solution):
        self.require_enabled(s)
        self.text(solution)
        row = self.db.execute("SELECT * FROM cases WHERE guild=? AND channel=? AND id=?", (*s.tenant, case)).fetchone()
        if not row or row['status'] != 'candidate' or (row['author'] != s.user and not s.moderator):
            raise Denied("후보 사례의 질문자 또는 이 채널의 메시지 관리 권한자만 확정할 수 있습니다.")

    def resolve(self, s, case, solution, message):
        with self.db:
            self.check_resolution(s, case, solution)
            solution = self.text(solution)
            self.db.execute("UPDATE cases SET status='confirmed', solution=?, resolver=?, resolution_channel=?, resolution_message=? WHERE guild=? AND channel=? AND id=?",
                            (solution, s.user, s.conversation, message, *s.tenant, case))

    def knowledge(self, s):
        if not s.guild or s.bot or not self.enabled(s):
            return []
        return [dict(r) for r in self.db.execute("SELECT * FROM cases WHERE guild=? AND channel=? AND status='confirmed' ORDER BY id DESC LIMIT 20", s.tenant)]

    def search_knowledge(self, s, question):
        """Rank a fixed tenant-local window; never fall back to unrelated rows."""
        if not s.guild or s.bot or not self.enabled(s):
            return []
        query = lexical_features(self.text(question))
        if not query:
            return []
        rows = self.db.execute(
            "SELECT * FROM cases WHERE guild=? AND channel=? AND status='confirmed' "
            "ORDER BY id DESC LIMIT ?", (*s.tenant, SEARCH_WINDOW))
        ranked = []
        for row in rows:
            features = lexical_features(row['question']) | lexical_features(row['solution'])
            score = len(query & features)
            if score:
                ranked.append((score, row['id'], dict(row)))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[:SEARCH_RESULTS]]

    def history(self, s):
        if not s.guild or s.bot or not self.enabled(s):
            return []
        rows = self.db.execute("SELECT question FROM turns WHERE guild=? AND channel=? AND conversation=? AND user=? ORDER BY id DESC LIMIT 8", (*s.tenant, s.conversation, s.user)).fetchall()
        return [r[0] for r in reversed(rows)]

    def reset(self, s):
        self.require_enabled(s)
        self._cancel(lambda op: op.scope.tenant == s.tenant
                     and op.scope.conversation == s.conversation and op.scope.user == s.user)
        with self.db:
            self.db.execute("DELETE FROM turns WHERE guild=? AND channel=? AND conversation=? AND user=?", (*s.tenant, s.conversation, s.user))

    def forget(self, s, case=None):
        if not s.guild or s.bot or not s.admin:
            raise Denied("서버 관리자만 사례를 삭제할 수 있습니다.")
        with self.db:
            if case is None:
                self.db.execute("DELETE FROM cases WHERE guild=? AND channel=?", s.tenant)
            else:
                cur = self.db.execute("DELETE FROM cases WHERE guild=? AND channel=? AND id=?", (*s.tenant, case))
                if not cur.rowcount:
                    raise Denied("이 채널에 해당 사례가 없습니다.")
            self.db.execute("DELETE FROM turns WHERE guild=? AND channel=?", s.tenant)
        self._cancel(lambda op: op.scope.tenant == s.tenant)

    def delete_user(self, s):
        if not s.guild or s.bot:
            raise Denied("서버의 사용자만 삭제할 수 있습니다.")
        self._cancel(lambda op: op.scope.guild == s.guild and op.scope.user == s.user)
        with self.db:
            affected = self.db.execute("SELECT DISTINCT channel FROM cases WHERE guild=? AND (author=? OR resolver=?)", (s.guild, s.user, s.user)).fetchall()
            for row in affected:
                self._cancel(lambda op: op.scope.tenant == (s.guild, row[0]))
            self.db.execute("DELETE FROM cases WHERE guild=? AND (author=? OR resolver=?)", (s.guild, s.user, s.user))
            self.db.execute("DELETE FROM turns WHERE guild=? AND user=?", (s.guild, s.user))

    def delete_sources(self, guild, channel, messages):
        # Gateway deletion metadata only: never fetch or ingest message content.
        with self.db:
            for message in messages:
                # The receipt ID may not have returned yet. Fail closed for active
                # receipt submissions in this exact guild/conversation; unrelated
                # tenants are unaffected and no message-ID tombstones are kept.
                self._cancel(lambda op: op.awaiting_receipt
                             and op.scope.guild == guild
                             and op.scope.conversation == channel)
                rows = self.db.execute("SELECT channel FROM cases WHERE guild=? AND ((source_channel=? AND question_message=?) OR (resolution_channel=? AND resolution_message=?))", (guild, channel, message, channel, message)).fetchall()
                if rows:
                    self.db.execute("DELETE FROM cases WHERE guild=? AND ((source_channel=? AND question_message=?) OR (resolution_channel=? AND resolution_message=?))", (guild, channel, message, channel, message))
                    for row in rows:
                        self._cancel(lambda op: op.scope.tenant == (guild, row[0]))
                        self.db.execute("DELETE FROM turns WHERE guild=? AND channel=?", (guild, row[0]))

    def delete_channel(self, guild, channel):
        self._cancel(lambda op: op.scope.guild == guild
                     and channel in (op.scope.channel, op.scope.conversation))
        with self.db:
            parents = self.db.execute("SELECT DISTINCT channel FROM cases WHERE guild=? AND (channel=? OR source_channel=? OR resolution_channel=?)", (guild, channel, channel, channel)).fetchall()
            self.db.execute("DELETE FROM cases WHERE guild=? AND (channel=? OR source_channel=? OR resolution_channel=?)", (guild, channel, channel, channel))
            self.db.execute("DELETE FROM channels WHERE guild=? AND channel=?", (guild, channel))
            self.db.execute("DELETE FROM turns WHERE guild=? AND (channel=? OR conversation=?)", (guild, channel, channel))
            for row in parents:
                self._cancel(lambda op: op.scope.tenant == (guild, row[0]))
                self.db.execute("DELETE FROM turns WHERE guild=? AND channel=?", (guild, row[0]))

    def delete_guild(self, guild):
        self._cancel(lambda op: op.scope.guild == guild)
        with self.db:
            for table in ('channels', 'cases', 'turns'):
                self.db.execute(f"DELETE FROM {table} WHERE guild=?", (guild,))

    def close(self):
        self.db.close()

    def enabled(self, s):
        return bool(self.db.execute("SELECT 1 FROM channels WHERE guild=? AND channel=?", s.tenant).fetchone())

    def configure(self, s, enabled):
        if not s.admin or s.bot or not s.guild:
            raise Denied("서버 관리자만 채널 설정을 변경할 수 있습니다.")
        self._cancel(lambda op: op.scope.tenant == s.tenant)
        with self.db:
            if enabled:
                self.db.execute("INSERT OR IGNORE INTO channels VALUES (?, ?)", s.tenant)
            else:
                self.db.execute("DELETE FROM channels WHERE guild=? AND channel=?", s.tenant)
                self.db.execute("DELETE FROM cases WHERE guild=? AND channel=?", s.tenant)
                self.db.execute("DELETE FROM turns WHERE guild=? AND channel=?", s.tenant)
