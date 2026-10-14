from dataclasses import fields
import pytest
from helperbot.admission import Limits


@pytest.mark.parametrize('value', [0, -1, True, 1.5, '2', None, 1000000000])
def test_each_limit_rejects_invalid_values_without_echo(value):
    for field in fields(Limits):
        with pytest.raises(ValueError, match='Invalid admission configuration'):
            Limits(**{field.name: value})


@pytest.mark.parametrize('values', [
    {'user_requests': 21}, {'user_concurrent': 3},
    {'guild_concurrent': 8}, {'max_guilds': 1024, 'max_users_per_guild': 1024},
])
def test_inconsistent_or_excessive_limits_fail_closed(values):
    with pytest.raises(ValueError):
        Limits(**values)


def test_environment_configuration_is_allowlisted_and_validated():
    assert hasattr(Limits, 'from_env'), 'operator configuration missing'
    limits = Limits.from_env({'HELPER_ADMISSION_USER_REQUESTS': '3',
                              'UNRELATED_SECRET': 'never read'})
    assert limits.user_requests == 3
    assert limits.guild_requests == 20
    for bad in ('', '0', '-1', ' 3', '3.0', 'NaN', '秘密', '9' * 5000):
        with pytest.raises(ValueError) as exc:
            Limits.from_env({'HELPER_ADMISSION_USER_REQUESTS': bad})
        assert str(exc.value) == 'Invalid admission configuration'


def test_invalid_runtime_config_closes_database_without_login(tmp_path, monkeypatch):
    import sqlite3
    from helperbot import manage
    from helperbot.core import Store
    opened = []

    def record_store(path):
        store = Store(path)
        opened.append(store)
        return store

    monkeypatch.setattr(manage, 'Store', record_store)
    monkeypatch.setenv('HELPER_ADMISSION_USER_REQUESTS', 'invalid')
    paths = manage.Paths(tmp_path / 'config', tmp_path / 'data', tmp_path / 'units')
    with pytest.raises(ValueError, match='Invalid admission configuration'):
        manage.run(paths, check=True)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].db.execute('SELECT 1')
