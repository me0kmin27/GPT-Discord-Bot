import re
import json
from html.parser import HTMLParser


class SettingsForm(HTMLParser):
    """Collect the controls a browser submits, including selected modes."""
    def __init__(self, html):
        super().__init__()
        self.data = {}
        self.select = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and 'name' in attrs:
            self.data[attrs['name']] = attrs.get('value', '')
        elif tag == 'select':
            self.select = attrs['name']
        elif tag == 'option' and self.select:
            if self.select not in self.data or 'selected' in attrs:
                self.data[self.select] = attrs['value']

    def handle_endtag(self, tag):
        if tag == 'select':
            self.select = None


import pytest
pytest.importorskip('flask')
pytest.importorskip('flask_wtf')
from test_settings_ops import paths_at


def test_timeout_form_displays_current_defaults_limits_and_help(tmp_path):
    from helperbot.web_admin import bootstrap_admin, create_app
    from helperbot.settings_ops import read_settings
    from flask import render_template
    paths = paths_at(tmp_path)
    bootstrap_admin(paths, 'synthetic-test-passphrase-only')
    app = create_app(paths, port=8765)
    with app.test_request_context('/'):
        html = render_template('settings.html', config=read_settings(paths),
                               status={'available': False},
                               overview={key: {'status': {'available': False}}
                                         for key in ('bot', 'web')}, port=8765)
    form = SettingsForm(html).data
    for key, maximum in [('setup_timeout_seconds', 60), ('generation_timeout_seconds', 240)]:
        assert float(form[key]) == maximum
        control = re.search(r'<input id="' + key + r'"[^>]+>', html)[0]
        assert f'max="{maximum}"' in control
        assert f'기본 {maximum}초' in html
        assert f'0 초과 {maximum} 이하' in html
    assert '300초' in html
    assert '정리 시간은 별도' in html


def csrf(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))[1]


@pytest.mark.parametrize('options', [{}, {'setup_timeout_seconds': 60, 'generation_timeout_seconds': 240},
                                      {'setup_timeout_seconds': 3, 'generation_timeout_seconds': 20},
                                      {'setup_timeout_seconds': 2.5, 'generation_timeout_seconds': 45},
                                      {'setup_timeout_seconds': 3, 'web_search': 'disabled'},
                                      {'generation_timeout_seconds': 20, 'web_search': 'live',
                                       'model_reasoning_effort': 'high'}])
def test_model_only_rendered_form_preserves_all_other_config(tmp_path, options):
    from helperbot.web_admin import bootstrap_admin, create_app
    paths = paths_at(tmp_path)
    target = paths.config/'runtime.json'
    before = {'provider': 'codex-oauth', 'sync_guild': None,
              'codex': dict(options, model='before')}
    target.write_text(json.dumps(before))
    bootstrap_admin(paths, 'synthetic-test-passphrase-only')
    client = create_app(paths, port=8765).test_client()
    base = 'http://127.0.0.1:8765'
    page = client.get('/login', base_url=base)
    assert client.post('/login', base_url=base, headers={'Origin': base}, data={
        'password': 'synthetic-test-passphrase-only', 'csrf_token': csrf(page)}).status_code == 302
    page = client.get('/', base_url=base)
    data = SettingsForm(page.get_data(as_text=True)).data
    data['model'] = 'after'
    assert client.post('/save', base_url=base, headers={'Origin': base}, data=data).status_code == 302
    before['codex']['model'] = 'after'
    assert json.loads(target.read_text()) == before


@pytest.mark.parametrize('mode,value,status', [
    ('default', 'ignored', 302), ('override', '3', 302), ('override', '2.5', 302),
    ('override', 'maximum', 302), ('override', 'over_maximum', 400),
    (None, '3', 400), ('invalid', '3', 400), ('override', '', 400),
    ('override', 'nan', 400), ('override', 'inf', 400), ('override', '0', 400),
    ('override', '-1', 400), ('override', '241', 400), ('override', 'true', 400),
])
@pytest.mark.parametrize('key', ['setup_timeout_seconds', 'generation_timeout_seconds'])
def test_timeout_mode_validation_reset_and_stale_form(tmp_path, mode, value, status, key):
    from helperbot.web_admin import bootstrap_admin, create_app
    from helperbot.settings_ops import save_settings, read_settings
    paths = paths_at(tmp_path)
    target = paths.config/'runtime.json'
    original = {'provider': 'codex-oauth', 'sync_guild': 123, 'codex': {
        'model': 'before', 'model_reasoning_effort': 'high', 'web_search': 'live',
        'setup_timeout_seconds': 3, 'generation_timeout_seconds': 20}}
    target.write_text(json.dumps(original))
    bootstrap_admin(paths, 'synthetic-test-passphrase-only')
    client = create_app(paths, port=8765).test_client()
    base = 'http://127.0.0.1:8765'
    page = client.get('/login', base_url=base)
    assert client.post('/login', base_url=base, headers={'Origin': base}, data={
        'password': 'synthetic-test-passphrase-only', 'csrf_token': csrf(page)}).status_code == 302
    data = SettingsForm(client.get('/', base_url=base).get_data(as_text=True)).data
    if mode is None:
        del data[key + '_mode']
    else:
        data[key + '_mode'] = mode
    maximum = 60 if key == 'setup_timeout_seconds' else 240
    if value == 'maximum':
        value = str(maximum)
    elif value == 'over_maximum':
        value = str(maximum + 0.01)
    data[key] = value
    before_bytes = target.read_bytes()
    assert client.post('/save', base_url=base, headers={'Origin': base}, data=data).status_code == status
    if status == 400:
        assert target.read_bytes() == before_bytes
    else:
        expected = json.loads(before_bytes)
        if mode == 'default':
            del expected['codex'][key]
        else:
            expected['codex'][key] = float(value)
        assert json.loads(target.read_text()) == expected
    # A valid stale default-reset form must not erase a newer CLI override.
    data = SettingsForm(client.get('/', base_url=base).get_data(as_text=True)).data
    data[key + '_mode'] = 'default'
    save_settings(paths, {key: 4.5}, read_settings(paths)['revision'])
    latest = target.read_bytes()
    assert client.post('/save', base_url=base, headers={'Origin': base}, data=data).status_code == 400
    assert target.read_bytes() == latest


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
        'generation_timeout_seconds': '25', 'setup_timeout_seconds_mode': 'override',
        'generation_timeout_seconds_mode': 'override'})
    assert response.status_code == 302
    assert read_settings(paths)['values']['setup_timeout_seconds'] == 2.5
