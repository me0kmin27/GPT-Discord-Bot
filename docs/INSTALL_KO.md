# Linux 원커맨드 설치 (Codex OAuth 고정)

검토한 Git checkout에서 **일반 사용자 터미널**로 다음 한 줄을 실행합니다.

```bash
bash install.sh
```

원격 스크립트를 `curl | bash`로 실행하지 않습니다. 먼저 저장소를 clone하고
배포할 commit을 검토/checkout하세요. 설치기는 그 **정확한 HEAD**를 별도 checkout에
복사·고정합니다. 이후 원본 디렉터리를 지워도 설치 경로는 유지됩니다.
root/sudo 실행, OS 패키지 자동 설치, 자동 업그레이드, API 키 대체는 없습니다.
이 작업은 스크립트/CI 검증이며 실제 서버 배포·계정 로그인 완료가 아닙니다.

## 미리 준비할 것

- Linux, 비-root 전용 사용자, Git, Python 3.9+와 venv/ensurepip, Node.js 18+와 npm
  (CI: Ubuntu 24.04, Python 3.12, Node 22), 활성 user-systemd 세션.
- PyPI/npm 접속 및 Discord/OpenAI 외부 HTTPS 연결. Node는 서비스에서 실행하지 않고
  고정 Codex 패키지의 native executable을 사용합니다.
- 의존성 누락은 오류로 종료합니다. Debian/Ubuntu의 venv 오류는 관리자가 해당 배포판의
  `python3-venv`를 설치해야 합니다. 다른 배포판에 apt 명령을 강요하지 않습니다.
  관리자 패키지 설치는 설치기 밖에서 명시적으로 수행하세요.
- SSH 세션에서 `systemctl --user show-environment`가 성공해야 합니다. user manager가
  없는 컨테이너는 이 설치기 대상이 아닙니다. 기존 foreground CLI는 별도 사용 가능합니다.

## Discord Developer Portal — 사람이 필요한 입력

1. Developer Portal에서 Application을 만들고 **Bot** 페이지의 bot token을 준비합니다.
   OAuth client secret이나 Application ID는 bot token이 아닙니다. 토큰은 설치기의
   **숨김 입력 프롬프트에만** 붙여넣으세요. 채팅/명령행 인수/Git/셸 기록에 넣지 마세요.
2. Installation 또는 OAuth2 URL Generator에서 **Guild Install**, scope `bot`와
   `applications.commands`를 선택합니다. 대상 테스트 서버에 봇을 초대하려면 본인에게
   해당 서버 앱 설치/서버 관리 권한이 있어야 합니다.
3. 봇 권한: **View Channels, Send Messages, Send Messages in Threads, Embed Links**.
   Administrator는 부여하지 않습니다. Message Content, Server Members, Presence
   privileged intents는 필요 없으며 켜지 않습니다.
4. Discord 사용자 설정 → Advanced → Developer Mode를 켜고 테스트 서버를 우클릭하여
   **Copy Server ID**를 선택합니다. 설치기는 이 숫자를 요구합니다. 채널 ID나 앱 ID가 아닙니다.
5. 설치 뒤 서버 관리자가 부모 텍스트 채널에서 `/channel enabled:true`를 실행하고
   `/ask question:테스트 질문`을 확인합니다. DM/비공개 스레드/포럼은 지원하지 않습니다.

테스트 guild에만 명령을 sync합니다. 이 설정은 **명령 등록 범위**이지 Discord 서버
접근 제어/초대 차단 정책이 아닙니다. 이전 전역 명령을 자동 삭제하지 않습니다.
처음 사용하는 봇으로 테스트하세요. 전역 공개는 별도 검토 후 runtime.json의
`sync_guild`를 `null`로 명시하는 수동 운영입니다. 설치기는 기존 전역 설정을 발견하면
보존하고 중단합니다. `run --sync-guild ID`는 일회성 override입니다.

## 실행 중 수행되는 일

1. 의존성/권한/TTY/user manager 사전 점검.
2. 현재 HEAD의 별도 user-local checkout, 전용 venv, 앱 패키지 설치.
3. 앱 전용 prefix에 **@openai/codex@0.162.1** 설치. global npm 사용 없음.
4. 테스트 guild와 `codex-oauth`를 private `runtime.json`에 저장. 기존 설정/토큰은 보존.
5. Discord 토큰 숨김 입력 → 공식 `codex login --device-auth` 실행.
   **사용자가 공식 브라우저에서 계정 로그인/기기 코드 승인**해야 합니다.
   계정/워크스페이스의 device-code login 허용이 필요할 수 있습니다.
   기기 코드는 해당 터미널에 표시되며 설치기가 기록/재전송하지 않습니다.
6. 앱 전용 CODEX_HOME의 `login status`가 ChatGPT인지 확인(API 키 로그인은 거절),
   offline schema/provider 점검, user service 설치 → start → status → 3초 뒤 동일 PID/active 확인.

로그인 홈은 기존 `~/.codex`/Hermes 인증과 분리됩니다. 다른 앱의 세션을 복사하지 않습니다.
브라우저 흐름이 필요한 경우 설치된 관리 명령의 `codex-login --browser`를 해당 머신에서
직접 사용하고 설치기를 재실행하세요. 원격 headless 환경의 localhost callback 연결은
사용자가 직접 준비해야 합니다. 로그인 성공이 구독 entitlement/공개 hosted 운영 허가나
실제 추론 성공을 뜻하지는 않습니다.

**완료 메시지의 의미:** 소프트웨어 설치, 로컬 ChatGPT 로그인 상태, 프로세스 활성만 확인합니다.
Discord 인증/초대/명령 sync/실제 답변 생성·저장은 자동으로 검증했다고 주장하지 않습니다.
`/ask`의 실제 응답과 보존을 확인해야 운영 준비가 끝납니다. 생성 답변은 기존
SQLite 저장 흐름을 사용하며 자동 confirmed 사례가 되지는 않습니다.

## 경로와 재실행

기본 경로:

| 항목 | 경로 |
|---|---|
| 설치 소유권·고정 checkout·venv | `~/.local/share/discord-helper-install/` |
| 관리 실행 파일 | `~/.local/share/discord-helper-install/discord-helper` |
| Discord token | `~/.config/discord-helper/credentials.json` (600) |
| 공급자/테스트 guild | `~/.config/discord-helper/runtime.json` (600) |
| 데이터베이스 | `~/.local/share/discord-helper/state.db` |
| Codex 패키지 | `~/.local/share/discord-helper/tools/` |
| 앱 OAuth | `~/.local/share/discord-helper/codex/` |
| 공식 로그인 HOME | `~/.local/share/discord-helper/login-home/` |
| 사용자 unit | `~/.config/systemd/user/discord-helper.service` |

XDG_CONFIG_HOME/XDG_DATA_HOME도 지원하며 최초 설치 경로를 기록합니다. 재실행 때 바꾸면
중단합니다. 런처와 unit은 경로를 고정합니다. 설치 root는 위 고정 경로입니다.
같은 commit의 `bash install.sh`를 재실행하면 기존 토큰·DB·설정을 덮어쓰지 않습니다.
다른 commit으로 자동 업그레이드하지 않습니다. 기존 설치를 재개하려면:

```bash
bash ~/.local/share/discord-helper-install/app/install.sh
```

패키지/네트워크 실패 후 재실행 가능하지만, clone/venv가 중간에 끊겨 구조가 불완전하면
안전하게 중단하고 보존합니다. 표시된 소유 경로를 직접 확인한 뒤 복구하세요. 기존의
별도 도구 설치나 다른 Python을 가리키는 unit은 **자동 인수/삭제/교체하지 않습니다**.
기존 운영자는 서비스를 먼저 멈추고 private 백업·설치 경로·unit diff를 검토해야 합니다.

```bash
~/.local/share/discord-helper-install/discord-helper status
~/.local/share/discord-helper-install/discord-helper doctor
~/.local/share/discord-helper-install/discord-helper logs
~/.local/share/discord-helper-install/discord-helper restart
~/.local/share/discord-helper-install/discord-helper stop
```

`logs`는 자신의 터미널에서만 보고 민감한 운영 자료를 공개 이슈에 붙이지 마세요.
설치기 출력에 secrets를 포함한 디버그 traceback을 남기지 않으므로 패키지 실패는
의존성/네트워크/설치 경로를 확인해야 합니다.

## 무인 소프트웨어 준비 / CI

```bash
bash install.sh --help
bash install.sh --prepare-only
```

prepare-only는 실제 checkout/venv/패키지/Codex 설치와 offline DB schema 점검만 합니다.
**토큰 입력·OAuth·unit 설치·서비스 시작을 하지 않으며 NOT READY를 출력**합니다.
완전 무인 OAuth 승인 우회 기능은 없습니다. CI는 깨끗한 Linux 임시 HOME에서 이 경로와
반복 실행을 검증합니다. 별도 disposable user-systemd CI는 token/OAuth/Discord를
명시적 fixture로 대체하여 실제 unit 설치/시작/재시작/중지/정리를 검증합니다.
이는 실제 계정 로그인이나 운영 배포가 아닙니다.

## 부팅/로그아웃 후 유지와 제거 — 명시적인 운영 선택

설치기는 자동 enable/linger를 수행하지 않습니다. 검증 후 사용자가 선택할 경우에만:

```bash
systemctl --user enable discord-helper.service
# 시스템 관리자 정책 승인 하에 (본인 계정에 대해서만):
loginctl enable-linger "$USER"
```

linger는 관리자 인증이 필요할 수 있습니다. 자동 sudo는 없습니다. enable/is-enabled와
로그아웃·재부팅 뒤 상태는 운영자가 확인하세요.
제거 시 먼저 stop 및 (활성화했다면) disable하고 본인 소유 unit임을 확인한 뒤 unit만
수동 제거, `systemctl --user daemon-reload`를 수행합니다. 다른 사용자 서비스나
공유 systemd 디렉터리를 지우지 마세요. 앱 설치 디렉터리를 삭제하기 전 중지 확인이 필수입니다.
**config/data 삭제는 OAuth/Discord 인증과 사례 DB를 영구 삭제**합니다. 자동 uninstall은
제공하지 않습니다. private 백업과 인증 해지 여부를 별도로 결정하세요.

공식 참고: https://developers.openai.com/codex/auth ,
https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/cli/src/login.rs ,
https://discord.com/developers/docs/quick-start/getting-started
