# GPT-Discord-Bot — 채널별 해결 사례 도우미

**첫 로컬 마일스톤 + Linux 운영 CLI입니다. 완성된 공개 AI 서비스/배포 완료가 아닙니다.**

- Python / discord.py / SQLite로 실제 사례 저장·확정·조회·삭제 및 Discord 슬래시 명령을 구현했습니다.
- 최초 지식은 **0건**입니다. 사전 구축 코퍼스나 채팅 기록 전체 수집은 없습니다.
- 현재 `/ask`는 최근 사용자 확정 사례를 출처와 함께 보여줍니다. **Codex 생성은 항상 비활성**이며, 검색 결과를 AI 답변으로 가장하지 않습니다.
- Codex 로그인 도구는 제공하지만, 로그인 성공이 공개 다중 사용자 서비스 사용 허용이나 안전한 무도구 연동을 증명하지 않습니다. 개인 구독 재공유 가능 여부, 격리/무도구 강제, 공급자 정책 검증 전에는 실시간 공급자를 열지 않습니다. OpenAI API 키는 요구하지 않습니다.

## Linux 빠른 설치

권장: 전용 **비-root** 사용자, Python 3.11+, `python3-venv`, 사용자 systemd. Git checkout에서 실행합니다. 시스템 패키지 설치와 계정 생성은 운영자가 별도 처리합니다. 이 프로젝트는 sudo, 방화벽 변경, 자동 서버 배포를 하지 않습니다.

```bash
git clone https://github.com/me0kmin27/GPT-Discord-Bot.git
cd GPT-Discord-Bot
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install '.[test]'
export PATH="$PWD/.venv/bin:$PATH"
discord-helper doctor
discord-helper run --check
discord-helper install
```

`install`은 현재 Python 경로를 고정한 **사용자 서비스** `discord-helper.service`를 설치하고 `daemon-reload`합니다. 자동 시작/부팅 활성화는 하지 않습니다. 동일한 설치는 반복 가능하며, 다른 내용의 기존 unit이나 인증 파일을 덮어쓰지 않습니다. 저장소/가상환경을 옮겼다면 기존 unit을 검토한 후 다시 설치해야 합니다. PATH 설정 대신 `.venv/bin/discord-helper`를 사용해도 됩니다. `pipx install .` 환경에서도 같은 실행 파일이 생성됩니다.

### Codex 설치·로그인 (선택, 추론 활성화와 별개)

Node.js/npm이 있는 환경에서:

```bash
discord-helper install-codex
discord-helper codex-login
# 기기 코드 로그인이 불가능하고 브라우저가 있는 경우:
discord-helper codex-login --browser
```

- 공식 `@openai/codex` 패키지를 사용자 데이터 디렉터리 아래 npm prefix에 설치합니다. `sudo`/전역 npm 설치는 하지 않습니다. 이 명령은 실행 시 npm의 배포 버전을 설치하므로 변경 사항을 검토하세요.
- 공식 `codex -c 'cli_auth_credentials_store="file"' login --device-auth`에 직접 위임합니다. 기기 코드 로그인을 계정/워크스페이스 보안 설정에서 허용해야 할 수 있습니다. 로그인은 운영자의 터미널과 공식 브라우저에서 직접 수행합니다. 코드/비밀번호/OAuth 토큰을 채팅에 보내지 마세요.
- `CODEX_HOME`은 이 앱 전용 디렉터리로 지정하며 API 키 환경 변수는 로그인 자식 프로세스에 전달하지 않습니다. 기존 `~/.codex`/Hermes 인증을 읽거나 복사하지 않습니다. Codex 인증 캐시도 봇 실행 시 읽지 않습니다.
- **현재 봇은 이 로그인으로 모델을 호출하지 않습니다.** 안전한 공개 연동이 검증되지 않아 실제 transport는 없습니다. 로그인 없이도 로컬 사례 기능을 사용할 수 있습니다.

### Discord 토큰 설정 → 시작 → 상태/로그 → 중지

```bash
discord-helper setup       # 로컬 숨김 입력 프롬프트, 기존 토큰 보존
discord-helper start
discord-helper status
discord-helper logs
discord-helper logs --follow
discord-helper restart
discord-helper stop
```

`DISCORD_BOT_TOKEN` 환경 변수로 안전하게 주입한 상태에서 `setup`을 실행할 수도 있습니다. 실제 토큰을 명령줄 인수, Git, 채팅, 셸 기록에 넣지 마세요. `start/restart/stop`은 systemctl 결과 뒤 활성 상태를 다시 확인합니다. `status` 비활성 반환 코드와 실패를 숨기지 않습니다. 프로세스 활성 상태는 Discord 로그인/명령 동기화 성공의 보증은 아닙니다.

- systemd user manager가 없는 컨테이너/서버/macOS에서는 `discord-helper run`으로 포그라운드 실행하고 Ctrl-C로 종료합니다. 이 모드에서 `start/stop/status/logs`는 사용할 수 없습니다.
- 단일 데이터 디렉터리에 한 프로세스만 실행하도록 파일 잠금을 사용합니다. 같은 DB를 별도 경로/저수준 API로 공유하는 다중 프로세스 운영은 지원하지 않습니다.
- 부팅/로그아웃 뒤에도 실행하려면 운영자가 별도로 user service enable 및 사용자 lingering 정책을 결정하세요. 도구는 이를 몰래 활성화하지 않습니다.
- 테스트 서버만 명령을 등록하려면 `discord-helper run --sync-guild 서버ID`를 사용합니다. 기본 서비스는 가입한 서버에 사용할 전역 명령을 동기화합니다. 이 버전의 systemd unit에는 테스트 서버 옵션이 없습니다.

### Discord 앱 권한

운영자가 Developer Portal에서 봇을 만들고 서버에 `bot`, `applications.commands` 권한 범위로 초대해야 합니다. 봇에는 대상 채널 보기, 메시지 보내기, 스레드 메시지 보내기, Embed Links가 필요합니다. 봇에 Administrator를 주지 마세요. Message Content / Members 특권 intent는 사용하지 않습니다. Guilds와 Guild Messages 이벤트는 삭제 메타데이터 처리에 사용하지만 메시지 캐시를 끄고 일반 메시지 처리기를 두지 않습니다.

관리자가 부모 텍스트 채널에서 `/channel enabled:true`로 명시적 참여를 켜야 합니다. 새 서버/채널은 기본 비활성입니다. DM, 비공개 스레드, 포럼/기타 채널은 이 마일스톤에서 거절합니다. 비공개 스레드 지식이 부모 채널로 새는 것을 막기 위한 제한입니다.

## 명령과 저장 경계

| 명령 | 동작 / 권한 |
|---|---|
| `/channel enabled:true` | 서버 관리자만 현재 부모 텍스트 채널 참여 설정 |
| `/channel enabled:false confirm_purge:true` | 비활성화하면서 채널 사례와 대화 삭제 |
| `/ask question:...` | 명시적 질문을 후보로 저장. 최근 확정 사례 최대 3건 조회. AI 생성 아님 |
| `/resolved case_id:... solution:...` | 원 질문자 또는 **현재 채널과 부모 채널의 메시지 관리 권한자**만 직접 작성한 해결 요약 확정 |
| `/reset` | 현재 사용자·대화의 문맥만 초기화. 후보/확정 사례는 유지 |
| `/forget case_id:숫자 confirm:true` | 서버 관리자: 현재 부모 채널에 속한 해당 사례 및 채널 문맥 삭제 |
| `/forget case_id:all confirm:true` | 서버 관리자: 현재 부모 채널 사례/문맥 전체 삭제 |
| `/privacy_delete confirm:true` | 현재 서버 전체에서 본인이 질문하거나 확정한 사례 및 본인 문맥 삭제 |

- 지식 키: `(guild_id, parent_channel_id)`. 서로 다른 서버/채널의 데이터를 가져오지 않습니다.
- 대화 키: 위 키 + `(실제 channel/thread_id, user_id)`. 스레드는 부모 지식을 공유하지만 서로의 문맥은 공유하지 않습니다. 문맥은 최근 질문 8개로 제한합니다.
- 사례 상태는 candidate → confirmed입니다. 봇 답변은 자동 확정되지 않으며 `/resolved`는 이미 확정된 사례를 덮어쓰지 않습니다. 잘못된 확정은 관리자 삭제 후 새 사례로 처리하세요.
- 질문 및 해결 요약은 공개 봇 접수 메시지의 embed로 남깁니다. DB 출처 ID는 존재하는 **접수 메시지 ID**이며 슬래시 interaction ID가 아닙니다. 질문자/확정자 ID와 실제 출처 채널/메시지를 저장합니다.
- 최근 확정 사례는 관련성/진실을 보증하지 않습니다. 임베딩/벡터 검색/모델 학습은 없습니다. 요약은 미신뢰 자료이며 시스템 명령이 아닙니다. 지시문과 자료를 공급자 요청의 별도 필드로 분리합니다. 프롬프트 문구만으로 도구 차단이 완성됐다고 주장하지 않습니다.
- 명령/출력에서 멘션 알림을 차단합니다. 질문·해결 요약은 2000자로 제한합니다. 공급자 오류의 민감한 내부 메시지는 공개하지 않습니다.

## 개인정보·운영 데이터

기본 경로 (XDG 환경 변수를 따름):

| 경로 | 용도 |
|---|---|
| `~/.config/discord-helper/credentials.json` | Discord 토큰, 디렉터리 700 / 파일 600 |
| `~/.local/share/discord-helper/state.db` | 사례/문맥 SQLite |
| `~/.local/share/discord-helper/codex/` | 선택적 앱 전용 Codex 인증. **공개 저장소/백업 금지** |
| `~/.config/systemd/user/discord-helper.service` | 토큰 없는 사용자 unit |
| `.runtime/` | 개발용 테스트 DB/진행 기록, Git 제외 |

`--config-dir`, `--data-dir`, `--unit-dir`는 하위 명령 앞에 지정할 수 있습니다. 기본 경로를 권장합니다. 심볼릭 링크 기반 인증/런타임 경로를 거절합니다. 운영 DB는 평문이므로 접근 통제/암호화 디스크/백업 정책이 추가로 필요합니다.

- SQLite `secure_delete=ON`; 삭제 요청은 DB에서 실제 행과 관련 문맥을 제거합니다. 처리 도중 삭제/설정 변경이 발생한 공급자 응답은 폐기합니다.
- 온라인으로 받은 접수 메시지/채널/스레드/서버 삭제 이벤트는 해당 로컬 데이터를 지웁니다. 오프라인 기간에 놓친 Discord 삭제/탈퇴 이벤트를 자동 재조정하지는 못합니다.
- 로컬 삭제 명령은 이미 게시된 Discord 메시지, 다른 사람이 복사한 내용, 외부 백업까지 지우지는 않습니다. Discord 게시물은 사용자/관리자가 별도로 삭제해야 합니다. 자기 원문을 자유 텍스트로 다른 사례에 복사한 경우 자동 추적하지 않습니다.
- 자동 보존기간/내보내기/탈퇴자 관리 UI는 아직 없습니다. 삭제하지 않은 명시적 사례는 계속 보관되므로 운영자가 삭제 정책을 안내해야 합니다.
- GitHub에는 소스·테스트·문서·CI만 백업합니다. `.env*`, 인증 JSON, `.runtime`, SQLite, 로그, 가상환경은 제외합니다. 경로를 바꿨다면 커밋 전 반드시 검토하세요. `.gitignore`가 비밀 탐지/삭제를 대신하지 않습니다.

## 개발·검증

```bash
mkdir -p .runtime
.venv/bin/python -m pytest -q --basetemp=.runtime/pytest
.venv/bin/python -m compileall -q helperbot
discord-helper --config-dir "$PWD/.runtime/check/config" --data-dir "$PWD/.runtime/check/data" run --check
```

테스트는 실제 SQLite, 명령 콜백, 설치 명령 생성/상태 읽기, 안전한 설정과 파일 잠금을 검증합니다. Discord HTTP/게이트웨이 및 systemctl 프로세스 호출 경계는 테스트 대역을 사용하며 이를 실서버 검증으로 부르지 않습니다. Linux에서는 생성 unit을 `systemd-analyze verify`로 검사합니다. CI는 Ubuntu Python 3.11/3.12에서 실행합니다.

현재 개발 머신은 macOS이며 Docker/systemctl/codex를 PATH에서 찾지 못했습니다. 실제 Linux user manager에서의 start/stop, 실제 Discord 로그인·권한·출처 링크, 실제 Codex 로그인은 별도 운영 검증이 남아 있습니다. 봇 토큰/서버 대상이 제공되지 않았고 배포하지 않았습니다.

## 공개 서비스 이전의 차단 항목

1. 독립 코드 검토 및 최종 브랜치 테스트/CI 통과.
2. Codex 구독의 공개 다중 사용자 사용 조건 확인, 인증/tenant 격리 및 **실제 무도구 강제** 확인. 검증 전 실시간 transport 추가 금지.
3. Discord 테스트 서버에서 설치/동기화/권한 변경/삭제 이벤트/공개 스레드 실검증.
4. Linux 실제 사용자 서비스 수명주기와 비밀 저장/복구 검증.
5. 요청 속도 제한, 저장량/보존기간, 모니터링, DB 마이그레이션/백업, 오프라인 삭제 재조정 등 운영 강화. 현재 버전을 무제한 공개 서비스로 배포하지 마세요.

## 확인한 공식 자료

- discord.py 2.7.1 배포 패키지의 `Interaction.permissions`, `original_response`, `guild_only`, 응답/명령 API docstring을 직접 확인했습니다. 문서 웹 접근은 403이어서 설치된 공식 패키지를 기준으로 구현했습니다.
- OpenAI Codex 공식 인증 문서: https://developers.openai.com/codex/auth
- OpenAI Codex 공식 CLI 문서: https://developers.openai.com/codex/cli
- OpenAI Codex 공식 설정 참조 (`cli_auth_credentials_store`): https://developers.openai.com/codex/config-reference

이 자료는 로그인 명령의 근거이지, 공개 봇에 개인 구독을 재공유해도 된다는 근거는 아닙니다.
