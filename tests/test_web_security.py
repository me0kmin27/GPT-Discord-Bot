"""Security regression tests use only disposable configuration and passwords."""
import json
import pytest
pytest.importorskip('flask')
pytest.importorskip('flask_wtf')
from helperbot.web_admin import bootstrap_admin, create_app
from helperbot.manage import ManagementError
from helperbot.settings_ops import read_settings, save_settings
from test_settings_ops import paths_at
from test_web_admin import csrf

BASE = 'http://127.0.0.1:8765'
PASSWORD = 'synthetic-test-passphrase-only'


@pytest.fixture
def web(tmp_path):
    paths = paths_at(tmp_path)
    bootstrap_admin(paths, PASSWORD)
    app = create_app(paths)
    app.config['TESTING'] = True
    return paths, app.test_client()


def login(client):
    page = client.get('/login', base_url=BASE)
    return client.post('/login', base_url=BASE, headers={'Origin': BASE}, data={
        'csrf_token': csrf(page), 'password': PASSWORD})


def test_bootstrap_is_private_non_overwriting_and_not_plaintext(web):
    paths, client = web
    target = paths.config/'web-admin.json'
    before = target.read_bytes()
    assert PASSWORD.encode() not in before
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ManagementError):
        bootstrap_admin(paths, 'another-synthetic-password')
    assert target.read_bytes() == before
    target.chmod(0o644)
    with pytest.raises(ManagementError):
        create_app(paths)


def test_login_rate_limit_is_global_not_forwarded_ip(web):
    _, client = web
    for index in range(6):
        page = client.get('/login', base_url=BASE)
        response = client.post('/login', base_url=BASE, headers={
            'Origin': BASE, 'X-Forwarded-For': '192.0.2.'+str(index)},
            data={'csrf_token': csrf(page), 'password': 'incorrect'})
        assert response.status_code == (401 if index < 5 else 429)


def test_logout_revokes_replayed_cookie_and_csrf(web):
    _, client = web
    assert login(client).status_code == 302
    cookie = client.get_cookie('discord_helper_admin', domain='127.0.0.1')
    page = client.get('/', base_url=BASE)
    assert client.get('/logout', base_url=BASE).status_code == 405
    assert client.post('/logout', base_url=BASE, headers={'Origin': BASE},
                       data={'csrf_token': csrf(page)}).status_code == 302
    client.set_cookie('discord_helper_admin', cookie.value, domain='127.0.0.1')
    assert client.get('/', base_url=BASE).status_code == 302


@pytest.mark.parametrize('path', ['/save', '/apply', '/logout'])
def test_mutations_require_origin_and_csrf(web, path):
    paths, client = web
    login(client)
    page = client.get('/', base_url=BASE)
    before = (paths.config/'runtime.json').read_bytes()
    assert client.post(path, base_url=BASE, headers={'Origin': BASE}).status_code == 400
    assert client.post(path, base_url=BASE, data={'csrf_token': csrf(page)}).status_code == 400
    assert client.post(path, base_url=BASE, headers={'Origin': 'null'},
                       data={'csrf_token': csrf(page)}).status_code == 400
    assert (paths.config/'runtime.json').read_bytes() == before


def test_peer_host_port_and_forwarded_headers_cannot_bypass_boundary(web):
    _, client = web
    assert client.get('/login', base_url='http://localhost:9999').status_code == 400
    assert client.get('/login', base_url=BASE, environ_overrides={'REMOTE_ADDR': '192.0.2.4'},
                      headers={'X-Forwarded-For': '127.0.0.1'}).status_code == 400
    response = client.get('/login', base_url=BASE, headers={'X-Forwarded-Host': 'evil.test'})
    assert response.status_code == 200
    assert 'evil.test' not in response.get_data(as_text=True)
    assert response.headers['Cache-Control'] == 'no-store'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
    cookie = response.headers['Set-Cookie']
    assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie


def test_save_and_service_errors_never_include_sensitive_files(web, monkeypatch):
    paths, client = web
    (paths.config/'credentials.json').write_text('synthetic-secret-marker')
    login(client)
    page = client.get('/', base_url=BASE)
    before = (paths.config/'runtime.json').read_bytes()
    response = client.post('/save', base_url=BASE, headers={'Origin': BASE}, data={
        'csrf_token': csrf(page), 'revision': read_settings(paths)['revision'],
        'scope': 'guild', 'sync_guild': '0', 'model': '<script>alert(1)</script>',
        'web_search': 'live', 'setup_timeout_seconds': '3', 'generation_timeout_seconds': '20'})
    assert response.status_code == 400
    assert (paths.config/'runtime.json').read_bytes() == before
    assert 'synthetic-secret-marker' not in response.get_data(as_text=True)
    assert '<script>' not in response.get_data(as_text=True)
    response = client.post('/apply', base_url=BASE, headers={'Origin': BASE}, data={
        'csrf_token': csrf(page), 'revision': read_settings(paths)['revision']})
    assert response.status_code == 400


def test_unverified_query_cannot_claim_save(web):
    _, client = web
    login(client)
    page = client.get('/?saved=1', base_url=BASE)
    assert '설정 저장 완료' not in page.get_data(as_text=True)


def test_atomic_failure_keeps_previous_config_and_unrelated_files(tmp_path, monkeypatch):
    paths = paths_at(tmp_path)
    target = paths.config/'runtime.json'
    before = target.read_bytes()
    import helperbot.settings_ops as ops
    def fail(*args):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(ops.os, 'replace', fail)
    with pytest.raises(OSError):
        save_settings(paths, {'model': 'test'}, read_settings(paths)['revision'])
    assert target.read_bytes() == before
    assert list(paths.config.glob('.settings-*')) == []


def test_supported_future_options_are_preserved_not_exposed(tmp_path, monkeypatch):
    paths = paths_at(tmp_path)
    import helperbot.codex_transport as transport
    original = transport.validate_options
    def future(options):
        original({k: v for k, v in options.items() if k != 'future_supported'})
        return options
    monkeypatch.setattr(transport, 'validate_options', future)
    target = paths.config/'runtime.json'
    config = json.loads(target.read_text())
    config['codex']['future_supported'] = {'internal': 'not-for-the-ui'}
    target.write_text(json.dumps(config))
    shown = read_settings(paths)
    assert 'not-for-the-ui' not in json.dumps(shown)
    save_settings(paths, {'model': 'test'}, shown['revision'])
    assert json.loads(target.read_text())['codex']['future_supported'] == {'internal': 'not-for-the-ui'}
