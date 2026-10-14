"""Deterministic admission tests: no clock sleeps or external services."""
from contextlib import ExitStack
import importlib.util
import pytest
from helperbot.core import Scope, Denied


def test_user_rate_shared_across_channels_but_not_guilds():
    assert importlib.util.find_spec('helperbot.admission'), 'admission missing'
    from helperbot.admission import Admission, Limits
    now = [0.0]
    gate = Admission(Limits(user_requests=2), clock=lambda: now[0])
    for channel in (10, 20):
        with gate.request(Scope(1, channel, channel, 100)):
            pass
    with pytest.raises(Denied):
        with gate.request(Scope(1, 30, 31, 100)):
            pytest.fail('user rate bypass')
    with gate.request(Scope(2, 10, 10, 100)):
        pass
    now[0] = 59.999
    with pytest.raises(Denied):
        with gate.request(Scope(1, 10, 10, 100)):
            pass
    now[0] = 60
    with gate.request(Scope(1, 10, 10, 100)):
        pass


def test_guild_rate_cannot_be_bypassed_by_rotating_users():
    from helperbot.admission import Admission
    gate = Admission(clock=lambda: 0)
    for user in range(20):
        with gate.request(Scope(1, 10, 10, user)):
            pass
    with pytest.raises(Denied):
        with gate.request(Scope(1, 20, 21, 200)):
            pytest.fail('guild rate bypass')
    with gate.request(Scope(2, 10, 10, 200)):
        pass


def test_concurrency_caps_leave_capacity_for_other_guilds_and_release():
    from helperbot.admission import Admission
    gate = Admission(clock=lambda: 0)
    with ExitStack() as active:
        active.enter_context(gate.request(Scope(1, 10, 10, 100)))
        with pytest.raises(Denied):
            with gate.request(Scope(1, 20, 21, 100)):
                pytest.fail('same user concurrency bypass')
        active.enter_context(gate.request(Scope(1, 20, 21, 101)))
        with pytest.raises(Denied):
            with gate.request(Scope(1, 30, 30, 102)):
                pytest.fail('guild concurrency bypass')
        for guild in (2, 3, 4):
            for user in (100, 101):
                active.enter_context(gate.request(Scope(guild, 10, 10, user)))
        with pytest.raises(Denied):
            with gate.request(Scope(5, 10, 10, 100)):
                pytest.fail('global concurrency bypass')
    # Rejected admissions consumed no user budget; exceptions release slots.
    for _ in range(5):
        with pytest.raises(RuntimeError):
            with gate.request(Scope(5, 10, 10, 100)):
                raise RuntimeError('synthetic')
    with gate.request(Scope(1, 10, 10, 100)):
        pass


def test_state_capacity_fails_closed_without_evicting_live_budgets():
    from helperbot.admission import Admission, Limits
    assert hasattr(Limits(), 'max_guilds'), 'bounded tracking missing'
    now = [0]
    gate = Admission(Limits(max_guilds=2, max_users_per_guild=2), clock=lambda: now[0])
    with gate.request(Scope(1, 10, 10, 100)):
        with gate.request(Scope(1, 10, 10, 101)):
            pass
        with gate.request(Scope(2, 10, 10, 100)):
            pass
        for scope in (Scope(3, 10, 10, 100), Scope(1, 10, 10, 102)):
            with pytest.raises(Denied):
                with gate.request(scope):
                    pass
        assert len(gate._users) == 3 and len(gate._guilds) == 2
        now[0] = 60
        # Expired inactive identities are reclaimed, but active one's cap survives.
        with pytest.raises(Denied):
            with gate.request(Scope(1, 20, 20, 100)):
                pass
        with gate.request(Scope(3, 10, 10, 100)):
            pass
        assert len(gate._users) == 2 and len(gate._guilds) == 2
    now[0] = 120
    with gate.request(Scope(4, 10, 10, 100)):
        pass
    assert len(gate._users) == len(gate._guilds) == 1


def test_guild_expiry_never_orphans_later_user_budgets():
    from helperbot.admission import Admission, Limits
    now = [0]
    gate = Admission(Limits(max_guilds=1), clock=lambda: now[0])
    with gate.request(Scope(1, 10, 10, 100)):
        pass
    now[0] = 30
    with gate.request(Scope(1, 10, 10, 101)):
        pass
    now[0] = 60
    with pytest.raises(Denied):
        with gate.request(Scope(2, 10, 10, 100)):
            pytest.fail('unexpired user tracking orphaned')
    assert set(g for g, u in gate._users) <= set(gate._guilds)
