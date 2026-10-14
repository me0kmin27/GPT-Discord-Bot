import re
import pytest
pytest.importorskip('flask')
pytest.importorskip('flask_wtf')
from test_settings_ops import paths_at


def csrf(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))[1]


def test_real_login_csrf_and_authenticated_settings(tmp_path):
    from helperbot.web_admin import bootstrap_admin, create_app
    paths = paths_at(tmp_path)
    bootstrap_admin(paths, 'synthetic-test-passphrase-only')
    app = create_app(paths, port=8765)
    app.config['TESTING'] = True
    client = app.test_client()
    base = 'http://127.0.0.1:8765'
    assert client.get('/', base_url=base).status_code == 302
    page = client.get('/login', base_url=base)
    assert page.status_code == 200
    assert client.post('/login', base_url=base, data={'password': 'anything'}).status_code == 400
    response = client.post('/login', base_url=base, headers={'Origin': base}, data={
        'password': 'synthetic-test-passphrase-only', 'csrf_token': csrf(page)})
    assert response.status_code == 302
    page = client.get('/', base_url=base)
    assert page.status_code == 200
    assert '설정' in page.get_data(as_text=True)
    assert 'synthetic-test-passphrase-only' not in page.get_data(as_text=True)
    assert client.get('/', base_url='http://evil.test:8765').status_code == 400
    assert client.post('/save', base_url=base, headers={'Origin': 'http://evil.test'},
                       data={'csrf_token': csrf(page)}).status_code == 400
    from helperbot.settings_ops import read_settings
    response = client.post('/save', base_url=base, headers={'Origin': base}, data={
        'csrf_token': csrf(page), 'revision': read_settings(paths)['revision'],
        'model': 'synthetic-model', 'model_reasoning_effort': 'low', 'web_search': 'live',
        'scope': 'guild', 'sync_guild': '456', 'setup_timeout_seconds': '2.5',
        'generation_timeout_seconds': '25'})
    assert response.status_code == 302
    assert read_settings(paths)['values']['setup_timeout_seconds'] == 2.5
