"""Synchronous SQLite boundary; never accepts raw channel history."""
from dataclasses import dataclass
from pathlib import Path
import sqlite3


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


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA foreign_keys=ON")
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
        self.db.commit()
        self.revision = 0

    def require_enabled(self, s):
        if not s.guild or s.bot or not self.enabled(s):
            raise Denied("DM/봇 입력 또는 비활성 채널에서는 사용할 수 없습니다.")

    @staticmethod
    def text(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise Denied("내용은 공백이 아닌 1~2000자여야 합니다.")
        return value.strip()

    def candidate(self, s, question, message):
        self.require_enabled(s)
        question = self.text(question)
        with self.db:
            cur = self.db.execute(
                "INSERT INTO cases (guild, channel, source_channel, author, question, question_message) VALUES (?,?,?,?,?,?)",
                (*s.tenant, s.conversation, s.user, question, message))
            key = (*s.tenant, s.conversation, s.user)
            self.db.execute("INSERT INTO turns(guild,channel,conversation,user,question) VALUES (?,?,?,?,?)", (*key, question))
            self.db.execute("DELETE FROM turns WHERE guild=? AND channel=? AND conversation=? AND user=? AND id NOT IN (SELECT id FROM turns WHERE guild=? AND channel=? AND conversation=? AND user=? ORDER BY id DESC LIMIT 8)", (*key, *key))
        return cur.lastrowid

    def resolve(self, s, case, solution, message):
        self.require_enabled(s)
        solution = self.text(solution)
        with self.db:
            row = self.db.execute("SELECT * FROM cases WHERE guild=? AND channel=? AND id=?", (*s.tenant, case)).fetchone()
            if not row or row['status'] != 'candidate' or (row['author'] != s.user and not s.moderator):
                raise Denied("후보 사례의 질문자 또는 이 채널의 메시지 관리 권한자만 확정할 수 있습니다.")
            self.db.execute("UPDATE cases SET status='confirmed', solution=?, resolver=?, resolution_channel=?, resolution_message=? WHERE guild=? AND channel=? AND id=?",
                            (solution, s.user, s.conversation, message, *s.tenant, case))

    def knowledge(self, s):
        if not s.guild or s.bot or not self.enabled(s):
            return []
        return [dict(r) for r in self.db.execute("SELECT * FROM cases WHERE guild=? AND channel=? AND status='confirmed' ORDER BY id DESC LIMIT 20", s.tenant)]

    def history(self, s):
        if not s.guild or s.bot or not self.enabled(s):
            return []
        rows = self.db.execute("SELECT question FROM turns WHERE guild=? AND channel=? AND conversation=? AND user=? ORDER BY id DESC LIMIT 8", (*s.tenant, s.conversation, s.user)).fetchall()
        return [r[0] for r in reversed(rows)]

    def reset(self, s):
        self.require_enabled(s)
        with self.db:
            self.db.execute("DELETE FROM turns WHERE guild=? AND channel=? AND conversation=? AND user=?", (*s.tenant, s.conversation, s.user))
        self.revision += 1

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
        self.revision += 1

    def delete_user(self, s):
        if not s.guild or s.bot:
            raise Denied("서버의 사용자만 삭제할 수 있습니다.")
        with self.db:
            self.db.execute("DELETE FROM cases WHERE guild=? AND (author=? OR resolver=?)", (s.guild, s.user, s.user))
            self.db.execute("DELETE FROM turns WHERE guild=? AND user=?", (s.guild, s.user))
        self.revision += 1

    def close(self):
        self.db.close()

    def enabled(self, s):
        return bool(self.db.execute("SELECT 1 FROM channels WHERE guild=? AND channel=?", s.tenant).fetchone())

    def configure(self, s, enabled):
        if not s.admin or s.bot or not s.guild:
            raise Denied("서버 관리자만 채널 설정을 변경할 수 있습니다.")
        with self.db:
            if enabled:
                self.db.execute("INSERT OR IGNORE INTO channels VALUES (?, ?)", s.tenant)
            else:
                self.db.execute("DELETE FROM channels WHERE guild=? AND channel=?", s.tenant)
                self.db.execute("DELETE FROM cases WHERE guild=? AND channel=?", s.tenant)
                self.db.execute("DELETE FROM turns WHERE guild=? AND channel=?", s.tenant)
        self.revision += 1
