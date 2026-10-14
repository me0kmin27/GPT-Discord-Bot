"""Process-local admission for a single event loop; never logs request data."""
from contextlib import contextmanager
from dataclasses import dataclass
import os
import time

from .core import Denied


@dataclass(frozen=True)
class Limits:
    user_requests: int = 5
    guild_requests: int = 20
    window_seconds: int = 60
    user_concurrent: int = 1
    guild_concurrent: int = 2
    global_concurrent: int = 8
    max_guilds: int = 128
    max_users_per_guild: int = 64

    def __post_init__(self):
        ceilings = {
            'user_requests': 60, 'guild_requests': 600, 'window_seconds': 3600,
            'user_concurrent': 4, 'guild_concurrent': 16, 'global_concurrent': 64,
            'max_guilds': 1024, 'max_users_per_guild': 1024,
        }
        for name, ceiling in ceilings.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError('Invalid admission configuration')
        if (self.user_requests > self.guild_requests
                or not self.user_concurrent <= self.guild_concurrent < self.global_concurrent
                or self.max_guilds * self.max_users_per_guild > 65536):
            raise ValueError('Invalid admission configuration')

    @classmethod
    def from_env(cls, environ=None):
        environ = os.environ if environ is None else environ
        values = {}
        for name in cls.__dataclass_fields__:
            raw = environ.get('HELPER_ADMISSION_' + name.upper())
            if raw is not None:
                if (not isinstance(raw, str) or not 1 <= len(raw) <= 4
                        or not raw.isascii() or not raw.isdecimal()):
                    raise ValueError('Invalid admission configuration')
                values[name] = int(raw)
        return cls(**values)


@dataclass
class Bucket:
    expires: float
    used: int = 0
    active: int = 0


class Admission:
    def __init__(self, limits=None, *, clock=time.monotonic):
        self.limits = limits or Limits()
        self.clock = clock
        self._users = {}
        self._guilds = {}
        self._active = 0

    @contextmanager
    def request(self, scope):
        now = self.clock()
        # Lazy expiry is bounded by configured cardinality. Never evict live
        # quotas (which would let identity churn reset another user's budget).
        for key, bucket in list(self._users.items()):
            if not bucket.active and now >= bucket.expires:
                del self._users[key]
        retained_guilds = {guild for guild, _ in self._users}
        for key, bucket in list(self._guilds.items()):
            if not bucket.active and now >= bucket.expires and key not in retained_guilds:
                del self._guilds[key]
        key = (scope.guild, scope.user)
        if ((scope.guild not in self._guilds
             and len(self._guilds) >= self.limits.max_guilds)
                or (key not in self._users
                    and sum(guild == scope.guild for guild, _ in self._users)
                    >= self.limits.max_users_per_guild)):
            raise Denied('요청 한도에 도달했습니다. 잠시 후 다시 시도하세요.')
        user = self._users.get(key)
        guild = self._guilds.get(scope.guild)
        if user is None:
            user = Bucket(now + self.limits.window_seconds)
        if guild is None:
            guild = Bucket(now + self.limits.window_seconds)
        for bucket in (user, guild):
            if now >= bucket.expires:
                bucket.used = 0
                bucket.expires = now + self.limits.window_seconds
        if (user.used >= self.limits.user_requests
                or guild.used >= self.limits.guild_requests
                or user.active >= self.limits.user_concurrent
                or guild.active >= self.limits.guild_concurrent
                or self._active >= self.limits.global_concurrent):
            raise Denied('요청 한도에 도달했습니다. 잠시 후 다시 시도하세요.')
        self._users[key] = user
        self._guilds[scope.guild] = guild
        user.used += 1
        guild.used += 1
        user.active += 1
        guild.active += 1
        self._active += 1
        try:
            yield
        finally:
            user.active -= 1
            guild.active -= 1
            self._active -= 1
