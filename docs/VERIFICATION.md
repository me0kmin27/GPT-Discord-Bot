# 검증 범위 및 인계

> **현재 구현 정정:** `codex-oauth`는 명시적 로컬 선택으로 실제 실행됩니다. 기본값만
> `disabled-codex`이며 고정 readiness 거절/zero-tools 선행 조건은 제거했습니다.
> 제한은 도구 영향을 줄일 뿐 도구 0개나 호스트 파일 읽기 격리를 보증하지 않습니다.
> PR12의 생성 답변 영속 저장도 통합했습니다. 기존 아래 마일스톤 수치·고정 gate
> 표현은 당시 기록이며 현재 계약은 [CODEX_TRANSPORT.md](CODEX_TRANSPORT.md)를 따릅니다.
> 실제 앱 로그인/라이브 추론·공개 hosted 허가·배포는 수행하지 않았습니다.


## 현재 증거 기준 — PR #2–#7 병합 후

- main `7f9f5ee6dd6b494ad2163b069e05a846d0c90061`; 원격 run `38556271591`의 headSha 일치 및 Python 3.11/3.12, systemd normal/failure-recovery 네 job 성공 재조회. 과거 PR별 정확한 최종 head/merge는 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)에 정리했습니다.
- 새 연결된 acceptance: `tests/test_release_acceptance.py`의 질문 → 확정 → 관련 검색 → 개인정보 삭제 → SQLite 재개방. 실제 Store/Service/DisabledCodex 및 합성 receipt ID, 네트워크/Discord 연결 없음.
- baseline: macOS **222 passed, 1 skipped**. 새 테스트 단독 **1 passed**. 삭제 no-op 음성 대조는 남아 있는 본인 문맥 단언에서 **1 failed**; production 소스 변경 없음. 이는 기존 동작의 회귀 검증이지 새 기능 TDD RED나 실제 결함 발견이 아닙니다.
- 추가 후 전체 macOS Python 3.9.6 실행: **223 passed, 1 skipped** (systemd parser 없음). `compileall helperbot tests`, `git diff --check`, 별도 빈 경로의 CLI doctor/run --check 성공: `credentials_present=False`, `6 commands; provider=disabled-codex; no network/login`.
- 초기 시스템 Python에는 pytest가 없어 기존 retrieval worktree 가상환경 인터프리터를 사용했습니다. 최초 basetemp 부모 누락 오류는 `mkdir -p .runtime` 후 해소했으며 제품 결함/RED로 계산하지 않습니다. 테스트 대상 모듈은 새 worktree입니다.
- 아래 과거 구현 head/테스트 수/“CI 대기·병합 전” 문구는 역사 기록이며 현재 상태가 아닙니다. 이번 최종 docs/test head의 원격 push/PR CI는 push 후 정확한 SHA로 조회해 PR 댓글/인계에 기록합니다. 독립 검토는 부모 작업자에게 요청하며 자체 검토로 대신하지 않습니다.


## PR #6: CI cleanup 소유권 및 실패 복구

- 기반 main: PR #5 merge `ef631d7cd1188384079f1571ab944b7e5dc12499`. production 코드/기본값/인증/공급자는 변경하지 않습니다.
- 관찰한 구현 head `2cbdf1484b0baec3003fbe6e8b71b6572e8546a6`: push run `38553448944`, PR run `38553456907` 모두 normal/failure-recovery 및 Python 3.11/3.12 성공. 문서·추가 guard 회귀 검사를 포함하는 최종 head는 새 CI 실행/로그를 읽고 PR 댓글과 인계에서 별도 확정합니다.
- push failure-recovery job `115816707446`: 실제 fixture PID 2453 시작 → 원래 `SystemExit(73)` → 실제 stop 반환 0에 대해 expected=99 assertion 주입 → daemon-reload/LoadState=not-found 및 unit/drop-in 삭제 PASS → passwd 삭제 뒤 owned home/runtime 양쪽 orphan 확인 → harness exit 73 → **별도 always 단계** manager/account/home/runtime/state 제거 PASS. 마지막 단계는 failure outcome, code 73, orphan_verified=true, cleanup success를 모두 검사합니다. 성공처럼 실패를 숨기는 `continue-on-error`가 아닙니다.
- runtime service는 정상 stop에서 디렉터리를 제거하므로, fault injection은 예약 UID 소유 runtime 디렉터리를 다시 만들고 identity를 기록해 orphan 경로 복구를 실제 실행합니다. 실제 userdel 실패나 SIGKILL 자체를 재현한 것은 아닙니다. fixture stop 명령 실패가 아니라 **stop 결과 assertion 실패**를 주입합니다.
- root-private `/run/dhci<RUN_ID><ATTEMPT>.owned` 상태에 useradd **이전** UID/계정 표식 intent, 생성된 home/runtime의 device/inode/owner를 저장합니다. 고정된 `/home/<user>`, `/run/user/<uid>`만 검사하며 기존 계정/group/home/state, UID 재사용·계정 교체·미확인 경로·symlink를 거절합니다. passwd 항목이 없어도 저장된 identity가 일치하는 orphan은 복구하고, readback 성공 뒤 상태를 지웁니다. 원래 실패 코드는 cleanup 오류에 덮이지 않습니다.
- 로컬 회귀는 실제 임시 디렉터리 삭제/unknown path·symlink 보존, orphan 복구, preexisting 계정/group/home 거절, 교체 계정/재사용 UID 거절, self-hosted guard, stop 오류 뒤 unit 삭제와 원래 실패 보존을 확인합니다. 계정/systemctl 경계는 대역이며 **실제 privileged Linux 증거는 위 CI**입니다. stop 지속/주입 경로는 수정 전 실패를 확인한 뒤 구현했습니다.
- 폐기 가능한 GitHub-hosted VM 전용이며 운영 정리 도구가 아닙니다. hard kill/VM 종료 때 trap/always 실행은 보장하지 않습니다. mkdir/chown/runtime 시작과 identity 저장 사이에 끊기면 미확인 경로를 안전하게 남길 수 있습니다. 동시 악성 privileged 작업에 대한 보안 경계가 아닙니다.
- fixture lifecycle은 live bot readiness가 아닙니다. 실제 봇 ExecStart/토큰/Discord/Codex, enable/linger·재부팅 지속성, 실서버 배포/비밀 복구 미검증. AF_UNIX는 fixture 제한일 뿐 CI 전체 네트워크 격리가 아닙니다.

## PR #5 기록: 실제 user-systemd fixture 검증 (과거 CI)

### 실제 Linux CI 관찰

- 코드 head `b292dd73579bbef16f27bd347e691913e7ae2553`, push run `38551300056`: Ubuntu 24.04.5/Python 3.12.15의 systemd-lifecycle 및 Python 3.11·3.12 회귀 job 성공.
- 실제 로그: start PID 2492 → restart PID 2504, 각 PID의 start/stop acknowledgement, ActiveState=inactive/MainPID=0/Result=success, unit 제거 후 LoadState=not-found, 계정/home/runtime 제거 PASS 확인. fixture와 live readiness를 로그에서 명시적으로 구분합니다.
- 최초 run `38551112831`은 별도 UID가 runner workspace를 읽을 수 없어 실패했습니다. runner 권한을 완화하지 않고 테스트 파일만 일회용 home에 복사하여 해결했습니다. 실패 실행도 계정/home/runtime cleanup PASS였습니다.
- 이 증거 이후 manager cleanup의 ActiveState=inactive readback을 추가했습니다. 문서 포함 최종 head는 CI를 다시 실행하고 PR에서 exact SHA/run을 읽어 인계합니다. 위 SHA는 자기참조 최종 hash가 아닌 관찰한 코드 head입니다.
- cleanup의 `not logged in or lingering` 및 mail spool 미존재 메시지는 이 계정이 로그인/linger/mail을 사용하지 않기 때문입니다. 제거 성공은 별도 readback으로 판단합니다. 기존 Actions Node 20 deprecation 경고는 남아 있으나 이 PR에서 무관한 action 업그레이드는 하지 않았습니다.


- `.github/workflows/ci.yml`의 `systemd-lifecycle`은 mock systemctl 없이 별도 일회용 사용자와 실제 `user@UID.service`를 사용합니다. runner에 로그인 세션이 없어도 테스트 계정의 manager를 명시적으로 시작하며, 실패는 skip/성공으로 위장하지 않습니다.
- `tests/systemd_lifecycle.py`: 설치된 `discord-helper` entry point로 install 두 번/start/status/restart/stop 호출. 원본 unit은 `unit_text(Paths)`와 완전히 같고 테스트 후에도 변하지 않습니다. fixture drop-in은 ExecStart만 stdlib 대기 프로세스로 바꾸고 AF_UNIX만 허용합니다. 공백/%/$ 경로, FragmentPath/DropInPaths, 상태/PID와 실제 SIGTERM 종료 기록을 확인합니다.
- `tests/systemd_fixture.py`는 네트워크/Discord/Codex를 호출하지 않습니다. management 자식 환경은 `env -i` allowlist이며 운영 인증 파일을 읽지 않습니다. credentials.json/state.db가 생기지 않음을 검사합니다.
- `tests/run_systemd_ci.sh`: GitHub-hosted Linux만 허용, 중복 계정 거절, 별도 UID manager 사용, enable/linger 없음. Python finally에서 stop/unit/drop-in 삭제 및 LoadState=not-found 확인. shell trap에서 manager/account/home/runtime 제거 확인. workflow `always()`는 실패/취소 후 추가 cleanup 경로입니다. runner 자체 강제 소멸은 코드 cleanup을 보장할 수 없으므로 hosted disposable runner만 사용합니다.
- 기존 단위 테스트의 systemctl 대역과 이 실제 통합 테스트를 구분합니다. live 봇 ExecStart 실행/토큰 로딩/Discord 연결·명령 권한·Codex 로그인·운영 재부팅 자동기동·실사용자 lingering은 이 검증의 범위 밖입니다. production 소스 변경이 없어 새 runtime flag나 TDD 대상 production 구현도 없습니다.
- 로컬 회귀: 175 passed, 1 skipped (macOS systemd parser 없음). Linux CI 통과는 최종 SHA의 실제 로그를 읽은 뒤 PR/인계에서 확정합니다.


## 로컬 실행 증거

- `python -m pytest -q --basetemp=.runtime/pytest`: **105 passed, 1 skipped** (macOS Python 3.9.6, receipt-race 수정 후).
- skip은 `systemd-analyze` 부재에 따른 실제 unit 파서 검사 1건입니다. Ubuntu CI에서는 실행 대상입니다.
- `python -m compileall -q helperbot`, `git diff --check`: 성공.
- `pip install -e '.[test]'`: 실제 패키지/console entry point 설치 성공. 초기 pip 21의 editable 지원 오류는 가상환경 안에서 pip 업그레이드 후 해결했습니다.
- `discord-helper doctor`: disabled-codex, credentials_present=False 확인.
- `discord-helper ... run --check`: `Offline check OK: 6 commands; provider=disabled-codex; no network/login` 확인.

초기 Ubuntu CI는 Git 제외 디렉터리 `.runtime`의 부모가 없는 상태에서 pytest `--basetemp`를 지정하여 실패했습니다. 로컬에서도 동일 오류를 재현했고 CI/문서에 `mkdir -p .runtime` 선행 단계를 추가했습니다. 최종 CI 성공은 최종 head에서 다시 확인해야 합니다. 이후 실제 Linux unit 파서는 인용된 `WorkingDirectory`를 거절했습니다. 모든 앱 경로가 절대 경로이므로 불필요한 지시문을 제거했고, 공백/퍼센트/달러가 포함된 데이터 경로로 파서 회귀 검사를 강화했습니다.

## 테스트 경계

- SQLite는 실제 임시 파일로 테스트합니다. 서버/채널/사용자/스레드 격리, 후보→확정, 권한 거절, 문맥 상한/초기화, 개인정보/메시지/채널/서버 삭제, 삭제 중 지연 응답 무효화를 검증합니다.
- Discord command tree와 실제 콜백을 구성하고 HTTP 경계만 대역으로 대체합니다. 봇 로그인·실서버 권한·출처 링크 접근은 미검증입니다.
- systemd 설치 파일 생성/재설치/덮어쓰기 거절/경로 인용, 서비스 명령과 상태 재조회, 설정 권한/심볼릭 링크 방어, 공식 Codex 로그인 명령의 전용 인증 경로를 검증합니다.
- systemctl 및 Codex/npm 자식 호출은 테스트 대역이며 실제 서비스나 실제 로그인으로 부르지 않습니다. 생성 unit의 Linux 파서 검사는 별도 테스트입니다.
- 운영 토큰/개인 Codex/Hermes 인증 파일을 읽지 않았습니다. 테스트 토큰 문자열은 합성 fixture입니다. 배포, 공개 모델 호출, 실제 Codex 로그인은 실행하지 않았습니다.

## Receipt-await privacy race regression

- 기준 코드 `bcc38b1c0ebfe0f682c7dadfadaff3123ab75670`에서 실제 `/ask` 콜백의 receipt 응답 대기 중 삭제를 주입하여 **4 failed** (삭제된 질문이 SQLite에 삽입됨)를 확인한 뒤 수정했습니다. 이어 `/resolved` receipt 삭제 **4 failed**, 초기 receipt 대기 중 `/privacy_delete` **4 failed**, purge/re-enable **6 failed**, 다른 tenant/user 삭제가 service 응답을 취소하는 **3 failed**를 각각 확인하고 수정했습니다.
- `tests/test_receipt_races.py`의 초기 receipt 회귀 검사는 실제 command tree/callback, gateway callback, Service, disabled provider, SQLite를 사용하며 HTTP 호출만 대체합니다. 추가 service-await 검사 7건은 disabled provider의 실제 동작 앞에 Event gate만 두어 삭제 시점을 보장합니다(생성 응답 대역 아님). `send_message`와 `original_response` 양쪽 대기, single/bulk 삭제, 본인 삭제 및 아직 연결되지 않은 moderator resolver 삭제, reset/forget/채널 비활성화/스레드·채널·서버 삭제, 재활성화, 다른 서버·채널·사용자 격리, service 대기 중 근거 삭제, HTTP 실패/태스크 취소 후 정리를 검증합니다.
- 첫 수정 head의 Ubuntu Python 3.12 CI에서 추가 service-await 검사 4건이 실패했습니다. 즉시 종료하는 disabled provider의 `await`가 항상 스케줄러에 제어를 넘긴다는 테스트 가정 때문이었습니다. 초기 receipt 회귀 검사는 통과했고, 추가 검사에 명시적 Event gate를 넣어 삭제가 service 대기 중 발생하도록 수정했습니다. 이 CI 후속 수정은 테스트/문서만 변경하며 production 코드를 바꾸지 않습니다.
- receipt를 보내는 **첫 await 전** 활성 작업을 등록하고, await에서 돌아온 직후 취소를 검사한 다음 삽입/확정합니다. receipt ID를 아직 모를 때는 같은 guild/conversation의 어떤 메시지 삭제라도 해당 대기 작업을 보수적으로 취소합니다. ID를 확인한 뒤에는 이 보수적 모드를 종료합니다. 다른 guild/conversation의 무관한 삭제는 취소하지 않습니다.
- `/privacy_delete`는 기존 행이 없어도 해당 서버/사용자의 진행 중 작업을 무효화합니다. 삭제되는 사례가 다른 요청의 근거일 수 있으므로 실제 영향을 받는 parent-channel tenant의 요청도 무효화합니다. 전역 revision 대신 작업별 취소 플래그를 사용하여 다른 tenant의 삭제가 응답을 막지 않습니다.
- 영구 message-ID tombstone이나 사용자별 revision 사전은 없습니다. 메타데이터는 활성 작업 수에만 비례하며 성공/거절/예외/태스크 취소 시 `finally`에서 제거됩니다. 이미 취소된 작업은 재활성화로 복구되지 않고 새 명령은 정상 처리할 수 있습니다.

### 남아 있는 경계

- 단일 프로세스/이벤트 루프의 Store 및 전달된 gateway 이벤트에 대한 보장입니다. 오프라인 중 놓친 삭제 이벤트의 재조정이나 여러 프로세스 사이의 취소 전파는 구현하지 않았습니다.
- receipt ID를 모르는 짧은 구간에서 같은 conversation의 **무관한 메시지 삭제도 재시도를 요구할 수 있습니다**. 이는 무제한 tombstone 보관 대신 선택한 fail-closed 동작입니다.
- 삭제는 로컬 저장소와 아직 제출하지 않은 응답을 보호합니다. 이미 Discord에 제출된 receipt/embed, 진행 중인 HTTP 전송, 외부 백업을 원격으로 되돌리는 보장은 아닙니다. 사용자 안내대로 Discord 게시물/외부 백업 삭제는 별도입니다.
- live provider는 계속 disabled입니다. 실 Discord/모델 로그인, 배포, 운영 인증 파일 읽기는 하지 않았습니다. 최종 head의 원격 SHA/CI는 push 후 별도로 읽어 검증하며, 독립 검토 전 병합하지 않습니다.

## Stored-case capacity verification

- Base: `eaa39635fe7f553616140c6cccd0e2347eef1562`; independent worktree/branch, no schema migration.
- Three observed RED→GREEN slices: mixed candidate/confirmed overflow accepted; invalid environment values accepted or echoed in errors; full-tenant command still awaited its public receipt. All passed after their respective minimal implementation changes.
- Full local suite: **175 passed, 1 skipped** (macOS Python 3.9.6; only Linux systemd parser unavailable). `compileall`, whitespace check, doctor and `HELPER_CASES_PER_TENANT=500` offline CLI check succeeded.
- Added real SQLite coverage: total cap, configuration/default/edge validation, thread/user shared quota and cross-tenant negatives, restart with lowered cap without deletion, resolution while full, explicit cleanup reuse, two independent connections after successful preflights, insert/history rollback, lock failure and retry.
- Added actual command callbacks: known-full rejection before public receipt without consuming admission; competing insert at each receipt await; quota rejection releases pending/admission state; privacy/admin/reset/disable during pending receipt cannot resurrect a row; resolution allowed at capacity; reset cannot free a case slot. Existing HTTP/task-cancellation and receipt-deletion suites remain green.
- Preflight is advisory, **not a reservation**. A concurrent winner can fill capacity after the public embed is submitted; the loser persists neither case nor history and receives a private rejection. No claim of rolling back Discord HTTP. Final persistence serializes the count+insert under `BEGIN IMMEDIATE`, assuming cooperating writers use the same configuration. Multi-process cancellation remains unsupported.
- This bounds stored case rows per tenant, **not disk bytes or total history**. Existing over-limit rows remain. Tenant cardinality and conversation/user history key cardinality remain unbounded; SQLite files/journals and backups need separate operational limits. No automatic deletion or live provider/credentials/deployment changes.
- Remote exact SHA and CI are read after push and reported in the PR/handoff; parent performs independent review and any merge.

## 독립 검토 체크포인트

1. 최종 PR head의 CI와 테스트 재실행.
2. Discord 권한 경계/공개 스레드 정규화, 모든 SQL tenant 필터, 삭제 전파.
3. provider는 반드시 disabled이며 테스트 공급자를 실연동으로 광고하지 않는지 확인.
4. CLI의 credential 경로/권한/재설치 보존, systemd unit quoting/단일 프로세스 제한 확인.
5. 공개 저장소에 런타임 DB/인증/개인정보가 없고 개발 경로/토큰이 unit에 하드코딩되지 않았는지 확인.

GitHub 기능 브랜치의 백업은 승인되었지만, 작성자 자체 승인을 독립 검토로 취급하지 않습니다. 병합은 상위 작업자가 최종 head를 독립 검토한 뒤 처리합니다. 최종 원격 SHA와 CI 결과는 PR/인계 보고에서 확인합니다.
