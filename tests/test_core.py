import importlib.util


def test_channel_opt_in_is_persistent_and_admin_only(tmp_path):
    assert importlib.util.find_spec("helperbot") is not None, "core package missing"
    from helperbot.core import Store, Scope, Denied
    import pytest
    db = tmp_path / "state.db"
    s = Store(db)
    scope = Scope(1, 10, 10, 100)
    assert not s.enabled(scope)
    with pytest.raises(Denied):
        s.configure(scope, True)
    s.configure(Scope(1, 10, 10, 100, admin=True), True)
    s.close()
    s = Store(db)
    assert s.enabled(scope)
    assert not s.enabled(Scope(2, 10, 10, 100))
    assert not s.enabled(Scope(1, 11, 11, 100))
    s.close()
