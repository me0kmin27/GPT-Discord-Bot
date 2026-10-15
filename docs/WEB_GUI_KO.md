# CLI + 비공개 Web GUI

기존 `discord-helper` CLI를 유지하면서 같은 프로젝트에 서버 렌더링 한국어 웹 설정을
추가했습니다. Flask / Flask-WTF / Waitress 선택 의존성만 사용하며 프런트엔드 빌드,
외부 폰트, CDN, JavaScript, 공개 터널은 없습니다. Vercel 계열의 절제된 중립색·카드·
시스템 폰트 디자인을 참고했습니다.

## 설치와 최초 관리자

검토한 **현재 checkout**과 전용 가상환경에서 실행합니다. 아래는 신규/수동 설치 예시입니다.
이미 설치된 운영 봇은 [백업·수동 업그레이드 절차](UPGRADE_KO.md)를 먼저 따르세요.
소스 checkout만 바꿔서는 venv의 설치 패키지가 바뀌지 않습니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install '.[web]'
.venv/bin/discord-helper gui setup
.venv/bin/discord-helper gui run
```

- `gui setup`: 로컬 TTY의 숨김 입력으로 전용 관리자 비밀번호를 두 번 입력합니다.
  16–256자이며 Discord/ChatGPT 비밀번호와 별개입니다. 명령 인자·환경 변수·URL에
  비밀번호를 넣는 옵션은 없습니다. 비밀번호를 Git/채팅/로그에 저장하지 마세요.
- PBKDF2-SHA256 1,000,000회 해시만 config 디렉터리의 `web-admin.json`에 mode 600으로
  신규 저장합니다. 기존 관리자를 덮어쓰지 않습니다. 토큰/OAuth/사례 DB는 변경하지 않습니다.
- `gui run`: Waitress를 **127.0.0.1:8765**에서 전경 실행합니다. 중지는 Ctrl+C입니다.
  `--port`로 1024–65535 포트만 바꿀 수 있으며 공개 bind 옵션은 제공하지 않습니다.
- 브라우저에서 `http://127.0.0.1:8765`로 접속하고 관리자 비밀번호로 로그인합니다.
- 기존 `--config-dir`, `--data-dir`, `--unit-dir` 전역 옵션과 XDG 기본 경로를 그대로
  사용합니다. 전역 옵션은 `gui` 앞에 둡니다. GUI와 봇은 같은 config 디렉터리를 사용해야 합니다.
- `runtime.json`이 없으면 기존 CLI와 동일한 비활성 공급자 기본값을 보여줍니다.
  GUI는 공급자 선택·인증·토큰 발급 화면이 아니며 OAuth를 자동 활성화하지 않습니다.

기존 `bash install.sh`는 기존 설치/자동화 호환성을 위해 **봇 CLI 설치 흐름을 그대로**
유지합니다. GUI 의존성 설치·관리자 생성·GUI 실행을 자동으로 추가하지 않았습니다.
선택 GUI는 `[web]` 설치와 별도 `gui setup/run`으로 명시적으로 활성화하세요.
원커맨드 설치본은 위 `.venv`를 새로 만드는 대신 **기존 설치 venv**에 검토한 소스의
`[web]`를 설치합니다. 봇과 GUI가 같은 실행 패키지/config를 사용하도록 업그레이드 가이드의
중지·백업·pip 설치·readback을 먼저 완료하세요. 새 `install.sh` 재실행은 업그레이드가 아닙니다.

```bash
CLI="$HOME/.local/share/discord-helper-install/discord-helper"
"$CLI" gui setup       # 최초 관리자만; 기존 관리자면 생략
"$CLI" gui install     # unit 저장만, 봇 unit과 별개
"$CLI" gui start
"$CLI" overview
```

전경 실행을 원하면 `gui install/start` 대신 `"$CLI" gui run`을 사용합니다.
같은 포트에 전경/서비스를 동시에 실행하지 마세요. 관리자 생성만으로 GUI는 시작되지 않습니다.

## 원격 접근은 SSH 포워딩

승인된 SSH 접속이 있는 경우 클라이언트에서 실행합니다 (`USER@HOST`는 실제 승인된 대상):

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 USER@HOST
```

브라우저는 계속 `http://127.0.0.1:8765`를 사용합니다. 서버 GUI와 로컬 포워딩의 포트를
동일하게 맞추세요. exact Host/Origin 검사 때문에 다른 포트/도메인으로의 프록시는 거부됩니다.
서버 방화벽을 열거나 공유기 포워딩·공개 터널을 만들 필요가 없습니다.
현재 버전은 LAN HTTP/공인 HTTPS/SSO 프록시를 지원하지 않습니다. 외부 공개·SSO는
별도 접근 방식 결정과 TLS/프록시 신뢰/세션 정책 검토가 먼저 필요합니다.

## 설정과 적용

편집 가능한 값:

| GUI | 공통 runtime.json 키 | 의미 |
|---|---|---|
| 모델 식별자 | `codex.model` | 빈 값은 명시적 override 제거 |
| 추론 노력 | `codex.model_reasoning_effort` | 빈 값은 override 제거; 모델 지원 여부는 실제 요청 시 확인 |
| 호스팅 웹 검색 | `codex.web_search` | `disabled` / `live`만 지원, `live`는 검색 사용 |
| 명령 등록 범위/서버 ID | `sync_guild` | 특정 서버의 양의 ID 또는 전역 `null` |
| 준비 제한 시간 | `codex.setup_timeout_seconds` | 기본 3초, 0 초과 30 이하 |
| 생성 제한 시간 | `codex.generation_timeout_seconds` | 기본 20초, 0 초과 120 이하; 검색 포함 |

시간은 의도적 대기 또는 전체 요청 제한이 아닙니다. 숫자/유한성/범위는
`codex_transport.validate_options`와 기본 상수를 공유합니다.
[단계별 timeout 계약](timeout-contract.md)을 참고하세요.
모델/effort의 구문 검증은 공유 validator를 사용하며 원격 모델 가용성은 추측하지 않습니다.
전역 등록으로 변경해도 과거 guild 명령 삭제나 Discord 설치 권한을 자동 처리하지 않습니다.

1. **저장**은 현재 config를 다시 읽고 허용된 필드만 병합합니다. 지원되는 미표시 필드는
   보존하며 알 수 없는/지원되지 않는 스키마는 거부합니다. 다른 변경이 있으면 revision
   불일치로 실패합니다. 잠금 + 같은 디렉터리 임시 파일 + fsync + atomic replace + readback을
   사용합니다. config는 mode 600입니다. 봇을 재시작하지 않습니다.
2. **적용/재시작**은 별도 확인 페이지와 명시적 체크가 필요합니다. revision을 다시 확인한 뒤
   `systemctl --user restart discord-helper.service`만 argv 배열로 실행합니다.
   셸, 임의 서비스명, 임의 명령, 토큰/로그 조회는 없습니다. 진행 중 요청은 중단될 수 있습니다.
3. 성공 후 다시 `systemctl --user show`의 ActiveState/SubState/Result/ExecMainStatus/NRestarts만
   읽습니다. 실패/타임아웃/상태 불명은 그대로 표시하며 저장된 config를 되돌리지 않습니다.
4. **저장된 설정**과 **실제 적용 상태**는 별도입니다. 봇의 설정 보고 채널은 아직 없으므로
   실제 적용 값은 명확히 **확인되지 않음**으로 표시합니다. systemd active 스냅샷은 Discord
   로그인/명령 동기화/모델 응답/설정 적용의 증거가 아닙니다. 실제 Discord에서 별도 검증하세요.
   봇의 CLI override 또는 서비스 unit이 다른 config를 가리키면 GUI 저장값을 쓰지 않을 수 있습니다.

CLI도 같은 로직을 사용합니다:

```bash
discord-helper settings show
# show에서 받은 전체 revision을 사용합니다 (비밀 아님).
discord-helper settings set --revision REVISION --model MODEL --model-reasoning-effort low \
  --web-search live --setup-timeout-seconds 3 --generation-timeout-seconds 20
discord-helper settings set --revision NEW_REVISION --sync-guild 123456789
# 또는 명시적 전역 등록: --global-scope
discord-helper settings apply --revision LATEST_REVISION --confirm-restart
```

`settings show`의 `applied: null`도 미확인을 뜻합니다. `settings set/apply`와 Web GUI는
`settings_ops`를 공유합니다. 기존 `run/doctor/install/start/stop/restart/status/logs` CLI
행동과 자동화 인자는 변경하지 않았습니다. 기존 `restart`는 기존 lifecycle 동작을 유지하고,
새 설정 적용 흐름을 원하면 `settings apply`를 사용합니다.

## 선택 사용자 GUI 서비스

Linux 사용자 systemd가 있는 경우만 명시적으로 설치합니다. 기존 봇 서비스와 별개인
**같은 프로젝트의 GUI 프로세스**이며 같은 사용자/설정에 접근합니다.

```bash
discord-helper gui install     # unit 저장 + daemon-reload만, start/enable 하지 않음
discord-helper gui start
discord-helper gui status
discord-helper gui stop
```

고정 이름은 `discord-helper-web.service`입니다. 실행 Python/config 경로와 loopback 전용
`gui run`을 고정합니다. 같은 설치는 멱등적이며 다른 기존 unit은 덮어쓰지 않습니다.
자동 부팅 활성화, linger, sudo, 방화벽 변경은 수행하지 않습니다. `gui stop`은 이 사용자
서비스만 중지하며 전경 `gui run`에는 Ctrl+C를 사용합니다. GUI 서비스 설치/관리 명령은
CLI 전용이고 웹에서 관리 서비스를 중지/변경할 수 없습니다.

## 보안 범위와 한계

- 인증은 loopback에서도 필수. 전용 비밀번호 해시 외에 토큰/OAuth 내용·사례 DB·대화·원시 로그를
  읽거나 표시하지 않습니다. local assets만 사용하고 CSP는 스크립트·프레임·외부 리소스를 차단합니다.
- Flask-WTF CSRF는 로그인 포함 모든 POST에 적용합니다. exact Host+port, loopback 실제 peer,
  same-origin Origin, cross-site Fetch Metadata 거부를 함께 검사합니다. forwarded 헤더는 신뢰하지 않습니다.
- `Referrer-Policy: same-origin`은 다른 origin으로 referrer를 보내지 않으면서 정상 브라우저
  폼의 Origin을 보존합니다. `no-referrer`는 Chromium에서 POST Origin을 null로 바꿔 로그인을 막았습니다.
- HttpOnly/SameSite=Strict 쿠키, 서버 측 세션 ID 유효성/로그아웃 폐기, 절대 30분 만료,
  앱 재시작 시 전체 세션 무효화. HTTP loopback 전용이므로 Secure 쿠키는 사용하지 않습니다.
  이것은 LAN/public HTTP에 사용해도 된다는 뜻이 아닙니다. 다른 로컬 프로세스/동일 origin 앱,
  악성 브라우저 확장, root/같은 OS 계정의 파일 접근은 방어 경계 밖입니다.
- 로그인은 프로세스 전체에서 1분당 5회(성공 포함), 최대 32 세션, bounded request body입니다.
  단일 사용자·단일 Waitress 프로세스용입니다. 재시작하면 rate-limit 메모리가 초기화되며
  다른 로컬 사용자가 반복 실패로 1분 로그인 거부를 만들 수 있습니다. 분산/공개 서비스 방어가 아닙니다.
- 비밀번호 재설정: GUI를 먼저 중지하고 **web-admin.json만** 로컬에서 제거한 뒤 `gui setup`을
  실행합니다. 원래 봇 credentials.json, Codex auth, runtime.json, DB는 삭제하지 마세요.
- config 쓰기는 CLI/GUI 공통 lock으로 직렬화합니다. 수동 편집기는 이 잠금을 사용하지 않으므로
  동시 수동 편집은 피하세요. 운영 config/관리자 파일/DB는 Git에 넣지 않습니다.

## 검증

`tests/test_settings_ops.py`, `test_gui_cli.py`, `test_web_admin.py`, `test_web_security.py`,
`test_web_service.py`와 기존 전체 테스트를 실행합니다. Web 테스트는 `[web,test]`가 필요합니다.

`tests/web_browser_smoke.py`는 **설치된 wheel**의 실제 CLI/Waitress와 Chromium을 사용합니다.
임시 디렉터리의 synthetic 모델/서버 ID/일회성 관리자만 사용하고 종료 시 서버와 runtime을 제거합니다.
로그인/로그아웃, CLI 저장, GUI 저장 후 CLI readback, 잘못된 값 거부, CSRF 거부,
재시작 확인/취소, 390px 반응형, 외부 요청 없음 및 배포 패키지 CSS를 검증합니다.
실제 봇 서비스 재시작은 이 브라우저 테스트에서 하지 않습니다.

`web-evidence/manifest.json`과 7개 PNG는 synthetic 로컬 실행 증거입니다.
서비스 argv/readback/실패 경로는 단위 테스트로 검증했으며 **GUI user-systemd 설치/실행,
실제 봇 재시작, OAuth 추론/Discord 전달을 이 증거로 주장하지 않습니다**.
GitHub CI는 기존 전체 jobs에 추가로 Web 전체 테스트 및 설치 패키지 Chromium smoke를 실행합니다.
