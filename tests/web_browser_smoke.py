"""Real Chromium + packaged CLI/Waitress, exclusively disposable synthetic data.

Run after installing .[web] (not editable). No bot/service start is attempted.
"""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from urllib.error import URLError
from playwright.sync_api import sync_playwright
from helperbot.manage import Paths
from helperbot.web_admin import bootstrap_admin


def main():
    evidence = Path(sys.argv[1]).absolute()
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='web-gui-synthetic-', dir=os.environ.get('TMPDIR')) as directory:
        root = Path(directory)
        paths = Paths(root/'config', root/'data', root/'units')
        paths.config.mkdir(mode=0o700)
        runtime = paths.config/'runtime.json'
        runtime.write_text(json.dumps({'provider': 'codex-oauth', 'sync_guild': 123456789,
                                       'codex': {'model': 'synthetic-model', 'model_reasoning_effort': 'low'}}))
        runtime.chmod(0o600)
        password = secrets.token_urlsafe(24)
        bootstrap_admin(paths, password)
        cli = [sys.executable, '-m', 'helperbot.manage', '--config-dir', str(paths.config),
               '--data-dir', str(paths.data), '--unit-dir', str(paths.units)]
        def command(args):
            return subprocess.run(cli+args, cwd=root, check=True, text=True, capture_output=True).stdout
        shown = json.loads(command(['settings', 'show']))
        saved = json.loads(command(['settings', 'set', '--revision', shown['revision'],
                                    '--model', 'synthetic-cli-model', '--setup-timeout-seconds', '3',
                                    '--generation-timeout-seconds', '20']))
        assert saved['values']['model'] == 'synthetic-cli-model'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = 'http://127.0.0.1:'+str(port)
        process = subprocess.Popen(cli+['gui', 'run', '--port', str(port)], cwd=root,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shots = []
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Packaged GUI exited')
                try:
                    with urlopen(base+'/login', timeout=1) as response:
                        assert response.status == 200
                    break
                except URLError:
                    time.sleep(.1)
            else:
                raise RuntimeError('GUI did not become ready')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                context = browser.new_context(viewport={'width': 1280, 'height': 1000})
                page = context.new_page()
                requests = []
                page.on('request', lambda req: requests.append(req.url))
                def shot(name):
                    path = evidence/(name+'.png')
                    page.screenshot(path=str(path), full_page=True)
                    shots.append(path.name)
                page.goto(base)
                assert page.url == base+'/login'
                shot('01-login')
                page.get_by_label('관리자 비밀번호').fill(password)
                with page.expect_navigation() as navigation:
                    page.get_by_role('button', name='로그인', exact=True).click()
                if page.url != base+'/':
                    raise AssertionError('Login failed: '+str(navigation.value.status)+' '+page.locator('main').inner_text())
                page.wait_for_url(base+'/')
                assert page.locator('#model').input_value() == 'synthetic-cli-model'
                assert page.locator('strong').inner_text() == '확인되지 않음'
                assert page.locator('.card').first.evaluate('(e) => getComputedStyle(e).borderRadius') == '8px'
                shot('02-settings-desktop')
                page.locator('#model').fill('synthetic-web-model')
                page.locator('#setup_timeout_seconds').fill('2.5')
                page.get_by_role('button', name='설정 저장', exact=True).click()
                page.wait_for_url(base+'/')
                assert '설정 저장 완료' in page.get_by_role('status').inner_text()
                readback = json.loads(command(['settings', 'show']))
                assert readback['values']['model'] == 'synthetic-web-model'
                assert readback['values']['setup_timeout_seconds'] == 2.5
                assert readback['applied'] is None
                shot('03-saved-readback')
                page.locator('#model').fill('invalid model with spaces')
                page.get_by_role('button', name='설정 저장', exact=True).click()
                assert '올바르지 않습니다' in page.get_by_role('alert').inner_text()
                assert json.loads(command(['settings', 'show']))['revision'] == readback['revision']
                shot('04-validation-error')
                page.goto(base)
                # Real browser form submission without framework CSRF token must fail.
                page.locator('form[action="/save"] input[name="csrf_token"]').evaluate('(e) => e.remove()')
                page.get_by_role('button', name='설정 저장', exact=True).click()
                assert '요청을 확인할 수 없습니다' in page.get_by_role('alert').inner_text()
                shot('05-csrf-rejected')
                page.goto(base+'/apply')
                assert not page.locator('input[name="confirm"]').is_checked()
                shot('06-restart-confirmation')
                # Deliberately do NOT click restart: no live service is authorized here.
                page.get_by_role('link', name='취소', exact=True).click()
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                assert page.get_by_role('button', name='로그아웃', exact=True).bounding_box()['height'] <= 52
                shot('07-settings-mobile')
                page.get_by_role('button', name='로그아웃', exact=True).click()
                page.wait_for_url(base+'/login')
                assert all(url.startswith(base+'/') for url in requests)
                browser.close()
            assert not paths.data.exists(), 'GUI must never create/open the bot data DB'
            manifest = {'synthetic_only': True, 'screenshots': shots, 'count': len(shots),
                        'verified': ['packaged_waitress', 'cli_show_set_readback', 'browser_login_logout',
                                     'gui_save_cli_readback', 'validation_no_write', 'csrf_rejection',
                                     'restart_confirmation_cancel', 'responsive_390px', 'local_assets_only'],
                        'not_verified': ['live_systemd_restart', 'bot_applied_settings', 'Discord', 'OAuth_inference']}
            (evidence/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
            print(json.dumps(manifest, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
