# GPT-Discord-Bot — 채널별 해결 사례 도우미

**PR #2–#7의 로컬 사례 도우미·운영 CLI가 병합되었습니다. 완성된 공개 AI 서비스/배포 완료가 아닙니다.**

현재 판정·정확한 병합 SHA·사용자 결정·남은 유한 gates는 [릴리스 체크리스트](docs/RELEASE_CHECKLIST.md)를 기준으로 확인하세요.

- Python / discord.py / SQLite로 실제 사례 저장·확정·조회·삭제 및 Discord 슬래시 명령을 구현했습니다.
- 최초 지식은 **0건**입니다. 사전 구축 코퍼스나 채팅 기록 전체 수집은 없습니다.
- 현재 `/ask`는 질문과 어휘가 일치하는 사용자 확정 사례를 순위화하여 출처와 함께 보여줍니다. **Codex 생성은 항상 비활성**이며, 검색 결과를 AI 답변으로 가장하지 않습니다.
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
| `/ask question:...` | 명시적 질문을 후보로 저장. 질문 기반 어휘 검색으로 확정 사례 최대 3건 조회. AI 생성 아님 |
| `/resolved case_id:... solution:...` | 원 질문자 또는 **현재 채널과 부모 채널의 메시지 관리 권한자**만 직접 작성한 해결 요약 확정 |
| `/reset` | 현재 사용자·대화의 문맥만 초기화. 후보/확정 사례는 유지 |
| `/forget case_id:숫자 confirm:true` | 서버 관리자: 현재 부모 채널에 속한 해당 사례 및 채널 문맥 삭제 |
| `/forget case_id:all confirm:true` | 서버 관리자: 현재 부모 채널 사례/문맥 전체 삭제 |
| `/privacy_delete confirm:true` | 현재 서버 전체에서 본인이 질문하거나 확정한 사례 및 본인 문맥 삭제 |

- 지식 키: `(guild_id, parent_channel_id)`. 서로 다른 서버/채널의 데이터를 가져오지 않습니다.
- 대화 키: 위 키 + `(실제 channel/thread_id, user_id)`. 스레드는 부모 지식을 공유하지만 서로의 문맥은 공유하지 않습니다. 문맥은 최근 질문 8개로 제한합니다.
- 사례 상태는 candidate → confirmed입니다. 봇 답변은 자동 확정되지 않으며 `/resolved`는 이미 확정된 사례를 덮어쓰지 않습니다. 잘못된 확정은 관리자 삭제 후 새 사례로 처리하세요.
- 질문 및 해결 요약은 공개 봇 접수 메시지의 embed로 남깁니다. DB 출처 ID는 존재하는 **접수 메시지 ID**이며 슬래시 interaction ID가 아닙니다. 질문자/확정자 ID와 실제 출처 채널/메시지를 저장합니다.
- 어휘 일치 점수는 의미적 관련성/진실을 보증하지 않습니다. 임베딩/벡터 검색/모델 학습은 없습니다. 요약은 미신뢰 자료이며 시스템 명령이 아닙니다. 지시문과 자료를 공급자 요청의 별도 필드로 분리합니다. 프롬프트 문구만으로 도구 차단이 완성됐다고 주장하지 않습니다.
- 명령/출력에서 멘션 알림을 차단합니다. 질문·해결 요약은 2000자로 제한합니다. 공급자 오류의 민감한 내부 메시지는 공개하지 않습니다.

## 질문 기반 로컬 검색 (생성·모델 학습과 별개)

- 검색 대상은 **활성 `(guild_id, parent_channel_id)`의 confirmed 행만**입니다. 후보, 다른 서버/부모 채널은 SQL에서 먼저 제외합니다. 공개 형제 스레드는 기존 정책대로 같은 부모 지식을 공유합니다.
- 고정 검색 창은 **사례 ID 내림차순 최근 1000개 확정 행**입니다(확정 시각 순서 아님). 기존 tenant 인덱스와 parameter binding을 사용하며 입력을 SQL/FTS 문법으로 조립하지 않습니다. `OR`, `*`, `%`, 따옴표 등은 검색 연산자가 아닙니다. 질문 텍스트는 SQL에 전달하지 않습니다.
- 질문과 저장된 질문·해결 요약에 NFKC 유니코드 정규화와 casefold를 적용합니다. 문자/숫자 단어(`_` 제외) 및 **연속 한글 음절의 인접 2글자 조각**을 별도 특징으로 만듭니다. 예: `프린터가`와 `프린터`는 `프린`, `린터`를 공유하여 조사 차이에도 찾을 수 있습니다. 공백을 건너뛰어 조각을 만들지는 않습니다.
- 점수는 질문 특징과 사례 특징(질문 ∪ 해결 요약)의 **서로 다른 공통 특징 수**입니다. 단어/한글 조각은 각각 1점, 동일 단어의 반복은 가산하지 않습니다. 양수 점수 내림차순, 동점이면 사례 ID 내림차순으로 **최대 3개**를 반환합니다. 현재 질문만 검색에 사용하며 과거 대화로 무관한 결과를 끌어오지 않습니다.
- 질문·해결 요약은 기존 각 2000자 입력 한도를 유지합니다. 검색은 최대 1000행의 각 두 필드만 특징화하며 DB 전체나 다른 tenant를 Python에서 훑지 않습니다. 요청별 동기 로컬 계산이며 지연시간 SLA/분산 부하 제어는 아닙니다. 총 저장 상한을 늘리거나 기존 데이터가 초과해도 검색 창은 늘어나지 않습니다. 창 밖 자료는 **보존되지만 검색되지 않을 수 있습니다**.
- 점수가 0이거나 검색 특징이 없는 기호/이모지만 입력하면 **일치 사례 없음**으로 안내합니다. 무관한 최신 사례로 대체하거나 DB에 확정 사례가 아예 없다고 단정하지 않습니다. 다른 핵심어로 재질문할 수 있습니다. 질문 자체는 여전히 후보로 저장됩니다.
- 결과는 사용자가 작성한 해결 요약 일부와 **원래 해결 접수 메시지 링크**입니다. 검색용 정규화는 원문/출처를 바꾸지 않습니다. `/resolved`는 로컬 사례를 확정할 뿐, AI 훈련·파인튜닝·자동 학습을 하지 않습니다. 검색은 새 답변을 생성하지 않으며 **Codex 비활성, 외부 임베딩/모델 호출/API 키 대체 없음**을 유지합니다.

**한계:** 형태소 분석, 동의어/번역, 오탈자 교정, 의미 검색, 진실 판정은 없습니다. 한글 조사·어미/흔한 단어·짧은 단어 때문에 우연한 일치가 생길 수 있고, 띄어쓰기·활용·표기 차이는 누락을 만들 수 있습니다. 숫자/영문 단어는 정규화 후 단어 일치이며 부분 문자열 검색이 아닙니다. 결과는 검토할 참고 사례이지 정답/신뢰도 점수가 아닙니다. 검색 특징은 DB에 따로 저장/캐시하지 않아 삭제 후 재조회에 남지 않습니다. 기존 receipt/pending 삭제 취소, admission, 저장 용량 경계를 유지하며 오프라인 삭제 누락·이미 전송된 Discord 게시물·외부 백업 한계는 그대로입니다. 스키마 변경/데이터 마이그레이션/자동 삭제는 없습니다.

## 요청 admission / 운영 제한

`/ask`와 `/resolved`는 **같은 예산**을 사용합니다. 권한·채널 참여·입력 검증 뒤,
공개 접수 메시지/DB 쓰기/공급자 호출 **이전**에 동기적으로 허가합니다.
초과 요청은 내용/ID를 포함하지 않는 ephemeral 안내만 보내며 대기열·자동 재시도는 없습니다.
허가한 요청은 최종 Discord 응답 편집까지 동시 실행 슬롯을 점유합니다.
정상 종료, HTTP 오류, 공급자 오류/시간 초과, task 취소, 개인정보 무효화 종료 모두 슬롯을 반환합니다.
허가 후 실패·취소해도 속도 예산은 환불하지 않습니다.

환경 변수는 시작 시 한 번 읽습니다. 접두사는 **`HELPER_ADMISSION_`**입니다.

| 접미사 | 기본값 | 허용 범위 | 의미 |
|---|---:|---:|---|
| `USER_REQUESTS` | 5 | 1–60 | `(서버, 사용자)`별 창당 요청 |
| `GUILD_REQUESTS` | 20 | 1–600 | 서버 전체 창당 요청 |
| `WINDOW_SECONDS` | 60 | 1–3600 | monotonic clock 기반 고정 창 길이(초) |
| `USER_CONCURRENT` | 1 | 1–4 | `(서버, 사용자)` 동시 요청 |
| `GUILD_CONCURRENT` | 2 | 1–16 | 서버 전체 동시 요청 |
| `GLOBAL_CONCURRENT` | 8 | 1–64 | 클라이언트 전체 동시 요청 |
| `MAX_GUILDS` | 128 | 1–1024 | 메모리에 추적할 서버 수 |
| `MAX_USERS_PER_GUILD` | 64 | 1–1024 | 서버별 추적 사용자 수 |

추가 검증: 사용자 속도 ≤ 서버 속도, 사용자 동시 수 ≤ 서버 동시 수 **< 전체 동시 수**,
추적 서버 수 × 서버별 사용자 수 ≤ 65536. 정수만 허용하며 빈 값/0/음수/과대값/잘못된 조합은
시작을 실패시킵니다(제한 해제/기본값으로 조용히 복구하지 않음). 설정 원문은 오류에 노출하지 않습니다.
예: `HELPER_ADMISSION_USER_REQUESTS=3 discord-helper run --check`는 로그인 없이 설정을 검사합니다.
실행 시에도 같은 환경을 전달해야 하며, systemd 환경은 운영자가 별도로 설정해야 합니다.

- 채널/스레드를 바꿔도 같은 서버 사용자 예산을 공유합니다. 같은 사용자라도 다른 서버 예산은 독립입니다.
- 서버 동시 상한이 전체보다 작아 한 서버가 모든 슬롯을 독점할 수 없습니다. **공정 순서/예약 슬롯/무기아 보장**은 아니며, 여러 서버가 전체를 채우면 다른 서버도 거절됩니다. 부모 채널별 별도 예산은 없습니다.
- 고정 창은 최초 사용 시 시작하고 만료 후 새 창을 엽니다. 창 경계에서는 연속 burst가 가능하므로 sliding-window 보장이 아닙니다.
- 거절은 예산을 소비하거나 새 추적 항목을 만들지 않습니다. 추적 한도에서는 살아 있는 예산을 축출하지 않고 신규 ID를 거절합니다. 만료된 비활성 항목은 **다음 요청에서** 정리합니다. 활성 작업/아직 만료되지 않은 사용자 예산이 있는 서버는 유지합니다.
- 카운터/서버·사용자 ID는 프로세스 메모리에만 두고 로그/DB에 저장하지 않습니다. 개인정보 삭제가 남용 방지 예산을 초기화하지 않습니다. 만료 후 다음 요청 또는 프로세스 종료까지 해당 메타데이터가 남을 수 있습니다.
- `/reset`, `/privacy_delete`, `/forget`, `/channel`과 게이트웨이 삭제 이벤트는 제한 대상이 아니므로 포화 중에도 정리/비활성화가 가능합니다. 이 경로와 거절 안내 자체의 HTTP 부하는 이 제한의 보호 대상이 아닙니다.
- **단일 클라이언트/이벤트 루프/프로세스용**입니다. 재시작하면 예산이 초기화됩니다. 다중 인스턴스 합산, 저수준 `Service`/`Store` 직접 호출의 admission, 분산 DoS 방어는 구현하지 않았습니다. 저장 사례 수 제한은 아래 별도 경계입니다. HTTP가 끝나지 않은 요청은 종료/취소 전까지 슬롯을 유지하며, 개인정보 무효화가 HTTP 자체를 강제 취소하지는 않습니다.

## Tenant별 저장 사례 수 제한

`HELPER_CASES_PER_TENANT`는 **`(guild_id, parent_channel_id)`당 candidate + confirmed 합계**의
상한입니다. 기본 **1000건**, 허용 **1–100000**(ASCII 숫자 1–6자리, 0/빈 값/음수/공백/과대값 거절).
Store 생성 시 한 번 검증하며 잘못된 값으로는 DB를 열지 않습니다. 모든 tenant에 같은 설정을 적용하고
부모/공개 스레드/사용자 사이에 상한을 공유합니다. 다른 서버/부모 채널의 사용량은 독립입니다.
예: `HELPER_CASES_PER_TENANT=500 discord-helper run --check`.
실제 실행에도 동일한 환경을 전달하세요. systemd 환경은 운영자가 별도로 설정합니다.

- `/ask`는 권한/입력 검증 뒤 admission과 **공개 접수 전**에 현재 용량을 검사합니다.
  이미 가득 차면 입력 내용 없는 ephemeral 안내만 전송하고 admission 예산을 소비하지 않습니다.
- preflight는 **예약이 아닙니다**. receipt HTTP 대기 중 다른 요청이 마지막 슬롯을 쓰면
  공개 embed가 이미 남았어도 저장은 거절됩니다. 자동 원격 삭제/HTTP 취소는 하지 않습니다.
  최종 `Store.candidate()`는 `BEGIN IMMEDIATE` 안에서 활성 채널과 합계를 재검사하고 사례/문맥을
  함께 쓰거나 롤백합니다. 동일 SQLite 파일의 동시 연결도 check/insert를 직렬화하지만,
  운영은 여전히 단일 프로세스만 지원하며 모든 writer가 같은 설정/Store 경계를 써야 합니다.
  DB lock/I/O 실패도 쓰기를 진행하지 않으며 일반 오류 경로로 처리합니다.
- `/resolved`는 이미 저장된 행의 상태를 바꾸므로 **가득 차도 허용**합니다. 후보를 확정해도
  슬롯이 생기지 않습니다. 별도 상태별 quota/예약 카운터/스키마 마이그레이션은 없습니다.
- 기존 행은 자동 삭제하지 않습니다. 상한을 낮추어 기존 데이터가 초과해도 보존하고 신규
  후보만 차단합니다. 총수가 상한 **미만**이 되어야 새 후보를 저장합니다.
- `/privacy_delete`, 관리자 `/forget`·채널 비활성화 및 gateway 삭제는 계속 작동합니다.
  `/reset`은 문맥만 지우므로 사례 슬롯을 반환하지 않습니다. 삭제 중 pending 취소와
  실패/취소 시 admission 정리는 기존 finally 경계를 유지합니다. 후발 용량 거절도 rate 예산은 환불하지 않습니다.

**물리적 DB 크기/전체 디스크 상한이 아닙니다.** tenant 수 자체는 제한하지 않으며 기존 초과 데이터는
남습니다. `turns`는 `(tenant, conversation, user)`별 최근 8개일 뿐 전체 키 수/보존기간 상한이 없습니다.
사례 삭제 방식에 따라 다른 사용자의 오래된 문맥이 남을 수 있고, 사례 quota는 그 문맥의 전역
증가를 제한하지 않습니다. SQLite 페이지/인덱스/저널, 삭제 후 파일 공간 재사용, 로그·백업·Discord
게시물 크기도 이 quota의 대상이 아닙니다. 디스크 모니터링, 승인된 보존/정리 정책과 백업 관리는 별도입니다.

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

테스트는 실제 SQLite, 명령 콜백, 설치 명령 생성/상태 읽기, 안전한 설정과 파일 잠금을 검증합니다. 일반 단위 테스트는 Discord HTTP/게이트웨이 및 systemctl 호출에 대역을 사용합니다. Linux에서는 생성 unit을 `systemd-analyze verify`로 검사하고, CI 회귀 테스트는 Ubuntu Python 3.11/3.12에서 실행합니다.

별도 GitHub-hosted Ubuntu job은 일회용 비-root 계정과 **실제 user-systemd + 오프라인 fixture**로 install/start/status/restart/stop 및 정리를 검사합니다. 원래 unit은 유지하고 테스트용 drop-in만 fixture 실행으로 바꿉니다. 실패 복구 job은 실제 fixture 시작 뒤 원래 종료 코드 **73**과 stop 결과 assertion 실패를 주입합니다. unit/drop-in 삭제를 계속한 뒤 passwd 항목만 없고 소유 home/runtime이 남은 상황을 확인하고, 별도 `always()` 단계가 기록된 UID·경로 identity로 복구합니다. 의도적 실패 단계만 `continue-on-error`이며 마지막 단계가 원래 코드/실패 outcome·orphan 사전조건·복구 성공을 모두 요구합니다.

`tests/run_systemd_ci.sh`와 root 전용 `tests/systemd_ci_owner.py`는 **폐기 가능한 GitHub-hosted VM 전용 테스트 도구**입니다. 운영자 정리 명령이 아닙니다. root-private 상태에는 useradd 이전 예약 UID/계정 표식과 생성 경로의 device/inode/owner를 저장합니다. 기존 계정/group/home/state, 재사용 UID, 바뀐 계정, 알 수 없거나 교체된 경로·symlink는 인수하지 않습니다. 계정 삭제는 `userdel --remove` 대신 계정과 검증된 경로를 분리하고, 성공 readback 뒤 상태도 제거합니다. 원래 실패 코드는 cleanup 오류가 덮어쓰지 않으며 정상 본문 뒤 cleanup만 실패해도 job은 실패합니다.

이 검증은 **live bot readiness가 아닙니다**. Discord/Codex 인증·연결, 실제 봇 ExecStart/토큰 로딩, 부팅 지속성·enable/linger, 실서버 배포/비밀 복구는 검증하지 않았습니다. fixture의 AF_UNIX 제한이 dependency 설치를 포함한 CI 전체의 네트워크 격리를 뜻하지 않습니다. macOS에서는 실제 systemd 검증을 실행하지 않습니다. SIGKILL/VM 종료는 trap/always 실행을 보장하지 않으며, 경로 생성·chown과 identity 기록 사이에 중단되면 안전상 미확인 경로를 남겨 VM 폐기에 맡길 수 있습니다. 동시 악성 root 작업에 대한 보안 경계가 아니며 persistent/self-hosted runner에서 재사용하면 안 됩니다.

## 공개 서비스 이전의 차단 항목

1. 독립 코드 검토 및 최종 브랜치 테스트/CI 통과.
2. 운영자 단일 구독의 app-server 공개 hosted relay는 진행하지 않습니다. 생성 없는 pilot 또는 공식 승인 경로/별도 설계의 제품 결정이 먼저입니다. [공급자 결정](docs/RELEASE_CHECKLIST.md)의 근거와 인증/tenant 격리·실제 무도구 검증 gates를 충족하기 전 transport 추가 금지.
3. Discord 테스트 서버에서 설치/동기화/권한 변경/삭제 이벤트/공개 스레드 실검증.
4. 실제 user-systemd **오프라인 fixture** 수명주기는 CI에서 검증했습니다. 지정된 운영 대상의 실제 봇 ExecStart/비밀 저장·복구/선택한 부팅 지속성은 여전히 미검증입니다.
5. 단일 프로세스 요청 속도/동시 실행 제한은 구현했습니다. tenant별 사례 수 상한 외 전체 저장량/보존기간, 분산 운영 제한, 모니터링, DB 마이그레이션/백업, 오프라인 삭제 재조정은 남아 있습니다. 현재 버전을 무제한 공개 서비스로 배포하지 마세요.

## 확인한 공식 자료

- discord.py 2.7.1 배포 패키지의 `Interaction.permissions`, `original_response`, `guild_only`, 응답/명령 API docstring을 직접 확인했습니다. 문서 웹 접근은 403이어서 설치된 공식 패키지를 기준으로 구현했습니다.
- OpenAI Codex 공식 인증 문서: https://developers.openai.com/codex/auth
- OpenAI Codex 공식 CLI 문서: https://developers.openai.com/codex/cli
- OpenAI Codex 공식 설정 참조 (`cli_auth_credentials_store`): https://developers.openai.com/codex/config-reference

이 자료는 로그인 명령의 근거이지, 공개 봇에 개인 구독을 재공유해도 된다는 근거는 아닙니다.
