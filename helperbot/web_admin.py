"""Optional, authenticated loopback Web GUI for the existing CLI."""
from collections import deque
from datetime import timedelta
from functools import wraps
import getpass
import json
import os
import secrets
import stat
import threading
import time
import warnings

from flask import Flask, abort, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from .manage import ManagementError, private_dir, secure_create
from .settings_ops import read_settings, save_settings, service_status, apply_settings, operator_overview


def bootstrap_admin(paths, password=None):
    private_dir(paths.config)
    if password is None:
        if not os.isatty(0):
            raise ManagementError('GUI setup requires a local interactive terminal.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('Web GUI password (16+ characters): ')
            if password != getpass.getpass('Confirm password: '):
                raise ManagementError('Passwords differ.')
    if not isinstance(password, str) or not 16 <= len(password) <= 256:
        raise ManagementError('Password requires 16–256 characters.')
    value = {'password_hash': generate_password_hash(password, method='pbkdf2:sha256:1000000')}
    if not secure_create(paths.config/'web-admin.json', json.dumps(value)+'\n'):
        raise ManagementError('Existing GUI administrator preserved. Stop GUI and remove only web-admin.json locally to reset.')


def load_admin(paths):
    target = paths.config/'web-admin.json'
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ManagementError('Symlinked GUI configuration refused.')
    try:
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError()
            data = json.load(stream)
        value = data['password_hash']
        if not isinstance(value, str) or not value.startswith('pbkdf2:sha256:1000000$'):
            raise ValueError()
        return value
    except (OSError, ValueError, KeyError, TypeError):
        raise ManagementError('Private GUI administrator unavailable; run gui setup.') from None


def create_app(paths, *, port=8765):
    password_hash = load_admin(paths)
    app = Flask(__name__, template_folder='web_templates', static_folder='web_static')
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=16384,
                      MAX_FORM_MEMORY_SIZE=16384, MAX_FORM_PARTS=32,
                      SESSION_COOKIE_NAME='discord_helper_admin', SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict', SESSION_COOKIE_SECURE=False,
                      PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
                      SESSION_REFRESH_EACH_REQUEST=False, TRUSTED_HOSTS=['127.0.0.1', 'localhost'])
    allowed = {'127.0.0.1:'+str(port), 'localhost:'+str(port)}
    sessions = {}
    attempts = deque()
    auth_lock = threading.Lock()

    @app.before_request
    def boundary():
        if request.host not in allowed or request.remote_addr not in ('127.0.0.1', '::1'):
            abort(400)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if request.headers.get('Origin') != 'http://'+request.host:
                abort(400)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            abort(400)

    CSRFProtect(app)

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        # no-referrer makes Chromium form POST Origin null; retain same-origin
        # provenance while disclosing no referrer to other origins.
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    def authenticated(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            with auth_lock:
                valid = sessions.get(session.get('sid'), 0) > time.monotonic()
            if not valid:
                session.clear()
                return redirect(url_for('login'))
            return function(*args, **kwargs)
        return guarded

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        status = 200
        if request.method == 'POST':
            with auth_lock:
                now = time.monotonic()
                while attempts and attempts[0] <= now-60:
                    attempts.popleft()
                if len(attempts) >= 5:
                    error, status = '로그인 시도가 많습니다. 1분 후 다시 시도하세요.', 429
                else:
                    attempts.append(now)
                    password = request.form.get('password', '')
                    if len(password) <= 256 and check_password_hash(password_hash, password):
                        sessions.pop(session.get('sid'), None)
                        for key in list(sessions):
                            if sessions[key] <= now:
                                sessions.pop(key)
                        if len(sessions) >= 32:
                            sessions.pop(next(iter(sessions)))
                        session.clear()
                        session['sid'] = secrets.token_urlsafe(32)
                        session.permanent = True
                        sessions[session['sid']] = now+1800
                        return redirect(url_for('settings'))
                    error, status = '비밀번호를 확인하세요.', 401
        return render_template('login.html', error=error), status

    @app.post('/logout')
    @authenticated
    def logout():
        with auth_lock:
            sessions.pop(session.get('sid'), None)
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    @authenticated
    def settings():
        status = service_status()
        return render_template('settings.html', config=read_settings(paths), status=status,
                               overview=operator_overview(bot_status=status), port=port,
                               message='설정 저장 완료. 자동 적용이나 봇 재시작은 수행하지 않았습니다.' if session.pop('saved', False) else None)

    @app.post('/save')
    @authenticated
    def save():
        guild = request.form.get('sync_guild', '')
        scope = request.form.get('scope')
        if scope == 'global':
            guild = None
        elif scope == 'guild' and guild.isascii() and guild.isdigit():
            guild = int(guild)
        else:
            raise ManagementError('대상 서버 ID를 확인하세요.')
        changes = {key: request.form.get(key, '') for key in ('model', 'model_reasoning_effort', 'web_search')}
        changes['sync_guild'] = guild
        try:
            for key in ('setup_timeout_seconds', 'generation_timeout_seconds'):
                mode = request.form.get(key + '_mode')
                if mode == 'default':
                    changes[key] = ''
                elif mode == 'override':
                    changes[key] = float(request.form.get(key, ''))
                else:
                    raise ManagementError('제한 시간 기본값 또는 직접 지정을 선택하세요.')
        except ValueError:
            raise ManagementError('제한 시간은 숫자로 입력하세요.') from None
        save_settings(paths, changes, request.form.get('revision'))
        session['saved'] = True
        return redirect(url_for('settings'))

    @app.get('/apply')
    @authenticated
    def confirm():
        return render_template('confirm.html', config=read_settings(paths))

    @app.post('/apply')
    @authenticated
    def apply():
        status = apply_settings(paths, request.form.get('revision'), request.form.get('confirm') == 'restart')
        return render_template('result.html', status=status)

    @app.errorhandler(ManagementError)
    def management_error(error):
        return render_template('error.html', message=str(error)), 400

    @app.errorhandler(400)
    @app.errorhandler(413)
    def bad_request(error):
        return render_template('error.html', message='요청을 확인할 수 없습니다. 페이지를 새로 열어 다시 시도하세요.'), error.code

    @app.errorhandler(500)
    def server_error(error):
        return render_template('error.html', message='작업에 실패했습니다. 로컬 CLI에서 설정과 서비스를 확인하세요.'), 500

    # Never emit exception bodies, request values or credential material to logs.
    app.logger.disabled = True
    return app


def serve(paths, *, port=8765):
    from waitress import serve as waitress_serve
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ManagementError('GUI port must be 1024–65535.')
    app = create_app(paths, port=port)
    print(f'Private Web GUI: http://127.0.0.1:{port} (authentication required)')
    waitress_serve(app, host='127.0.0.1', port=port, threads=4,
                   clear_untrusted_proxy_headers=True, max_request_body_size=16384,
                   channel_timeout=30, connection_limit=32)
