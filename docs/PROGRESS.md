# 로컬 첫 마일스톤

## 후속 PR: 질문 기반 bounded lexical retrieval

- 기반 `origin/main` `21afcfc00ecc9913984c697f9c94e54b0f4eaf23`; 별도 `GPT-Discord-Bot-retrieval` worktree / `feat/relevant-case-retrieval`. 현재 Store/Service와 최초 README의 명시적 확정·출처·공급자 비활성 경계를 먼저 확인했습니다. 기존 worktree는 변경하지 않았습니다.
- `/ask`가 무관한 최신 3건을 보여주던 경로를 tenant-filtered confirmed 검색으로 교체했습니다. 최근 ID 1000행 안에서 정규화된 단어 + 한글 음절 bigram의 고유 교집합 수로 순위를 매기고, 동점 ID 내림차순·최대 3건·0점 제외를 적용합니다. 검색 창 밖 행은 삭제하지 않습니다.
- 후보 제외, 원래 해결 접수 메시지 인용, 정직한 no-match 안내. 기존 privacy/pending 취소·admission·capacity 유지. 스키마/마이그레이션/영구 검색 캐시/외부 의존성/모델 호출 추가 없음. Codex는 비활성이고 API 키로 대체하지 않습니다.
- 실제 RED→GREEN: 최신 무관한 `[26,25,24]` 반환 대신 관련 `[1]` 기대(1 failed) → Service/Store 검색 연결; 한글 조사·해결 요약·전각/분해형 입력(4 failed) → NFKC와 한글 bigram; 기존 사례가 있는데 “아직 확정된 사례 없음” 표시(3 failed) → 검색 범위 no-match 안내.
- 로컬 전체 **222 passed, 1 skipped** (macOS Python 3.9.6; systemd parser skip). 새 검색 테스트는 실제 SQLite와 disabled provider/명령 콜백을 사용합니다. tenant/후보 제외, SQL·FTS·wildcard 입력, 입력 길이, 고정 창 경계/원본 보존, 순위/동점/반복어, 삭제 9경로와 재등록을 검사합니다. 기존 callback 삭제 race는 실제 선택된 evidence ID까지 확인하도록 강화했습니다.
- `compileall`, `git diff --check`, CLI `run --check` 성공: 6 commands, disabled-codex, no network/login. Ubuntu Python 3.11/3.12 전체 및 systemd CI는 push 후 **정확한 최종 SHA**로 확인하여 PR/인계에 기록합니다. 이 문서가 원격 성공을 미리 주장하지 않습니다.
- 한계: 어휘 기반 휴리스틱은 의미/정확성을 보증하지 않으며 흔한 어미/짧은 단어에 오탐, 동의어/오타/띄어쓰기에 누락이 가능합니다. 최근 1000개 ID 창 밖 사례는 검색하지 않습니다. README에 검색 ≠ 생성 ≠ 모델 학습, 동기 계산/미제공 SLA 및 기존 운영 개인정보 경계를 설명했습니다.
- 독립 검토는 부모 에이전트에 인계합니다. **병합/배포/로그인/실서버 호출 없음**.

## PR #6: 일회용 CI cleanup 후속

- PR #5 merge `ef631d7cd1188384079f1571ab944b7e5dc12499` 기반 새 `GPT-Discord-Bot-cleanup` worktree/`ci/owned-cleanup`; 다른 worktree 보존.
- CI-only root-private UID/소유권 상태와 계정 없는 orphan home/runtime 복구, fixture stop assertion 실패 뒤 정리 지속, 원래 실패 보존. 임의 경로 삭제나 운영 cleanup CLI를 추가하지 않습니다.
- 구현 head `2cbdf1484b0baec3003fbe6e8b71b6572e8546a6`의 실제 GitHub-hosted push/PR CI 성공. failure-recovery는 실제 fixture 시작·stop assertion 오류·exit 73·owned orphan 사전조건·별도 always 복구를 확인했습니다. 최종 문서/test head는 재실행 후 PR 댓글에서 확정합니다.
- 상세 소유권 거절 경계/주입 방식/잔여 interruption window는 `VERIFICATION.md`와 README 참조. live bot/공급자/인증/운영 배포 범위는 그대로 닫혀 있습니다.

## PR #5 기록: 실제 Linux 사용자 systemd lifecycle

- 실제 Linux 코드 head `b292dd73579bbef16f27bd347e691913e7ae2553` / run `38551300056` 성공: PID 교체/종료, inactive 상태, unit 및 일회용 계정 정리 로그 확인. 최종 문서 head CI는 재확인 후 PR 인계. 상세 실패 원인/경계는 VERIFICATION 참조.

- 기반 PR #4 `18e0fbc6ea06ece4042ef7a6120ad81c5abffbb1`; 별도 `GPT-Discord-Bot-systemd` worktree/`ci/linux-user-service`. 기존 worktree 보존.
- production Python/CLI/unit 기본값 변경 없음. 테스트 전용 executable/drop-in으로 Discord 실행만 대체하고 실제 설치 console CLI와 실제 systemctl/user manager를 실행합니다.
- GitHub-hosted Ubuntu 24.04에 일회용 비-root 계정/user manager를 생성합니다. linger/enable 없이 종료 trap과 `always()` cleanup으로 manager/계정/home/runtime을 제거합니다. 기존 사용자 서비스는 건드리지 않습니다.
- 재설치 bytes/inode/mtime 보존, 미시작/미활성화, start/status/restart/stop 상태·PID·SIGTERM acknowledgement, inactive status exit=3, 중복 stop 및 unit 제거 readback을 검사합니다.
- macOS 로컬: **175 passed, 1 skipped**, bash syntax/compileall/diff 검사 통과. pip 21 editable 설치 실패 후 일반 wheel 설치로 검증했습니다. Linux 실제 결과는 push 뒤 CI 로그와 exact head로 별도 확인합니다.
- fixture lifecycle은 실제 봇 준비 완료가 아닙니다. Discord/Codex 로그인·네트워크·실서버 배포·병합 없음. 공급자 차단 유지. CI 의존성 설치에는 패키지 다운로드가 필요합니다.


- 공개 원격 저장소가 비어 있음을 확인하고 로컬 복제했습니다.
- 범위: SQLite 지식/권한 코어, Discord 명령 연결, 오프라인 자동 테스트.
- 추가 승인 범위: Linux 사용자 systemd 설치/설정/시작/중지/상태/로그 CLI 및 분리된 Codex 로그인 위임.
- 코어/Discord 명령/개인정보 삭제/공급자 차단/Linux 관리 CLI 구현 완료. 로컬 자동 테스트: 50 passed, 1 skipped (systemd parser 없음).
- 실제 console entry point를 설치하여 doctor 및 run --check 실행 성공 (6 commands, disabled-codex).
- Ubuntu CI와 독립 검토 결과는 PR의 최종 head에서 별도 확인해야 합니다.
- macOS 로컬 환경에는 docker/systemctl/codex 실행 파일이 PATH에 없습니다. Linux 실서비스 검증과 실제 로그인은 미실행입니다.
- Codex 구독의 공개 다중 사용자 서비스 사용 가능 여부 및 안전한 무도구 연동은 미확인입니다. 실제 공급자는 닫힌 상태로 유지합니다.
- GitHub에는 소스/테스트/문서만 백업합니다. `.env`, 인증 파일, 런타임 DB, 사용자 대화/개인정보는 제외합니다.
- 배포/로그인/실서버 호출/병합은 이번 작업에 포함하지 않습니다. 기능 브랜치는 독립 검토 후 병합 대상입니다.

## 후속 PR: bounded admission (2026-10-14)

- 기반: 병합된 PR #2 `4faee3042f02df8679fd3c388ab1fd0ac61e59e6`. 별도 worktree/`feat/bounded-admission` 브랜치에서 작업하며 기존 checkout은 수정하지 않았습니다.
- 최소 범위: 공개 `/ask`·`/resolved`에 공유 admission 적용. 서버·사용자별 속도, 사용자/서버/전체 동시 실행 상한, bounded 추적 상태, 설정 검증 및 실패/취소 정리. 지식의 `(guild, parent_channel)` 격리 및 공급자 차단 경계는 변경하지 않았습니다.
- 기본 60초 사용자 5회/서버 20회, 동시 사용자 1/서버 2/전체 8. 서버 추적 128개·서버당 사용자 64개. 세부 범위·환경 변수·한계는 README에 기록했습니다.
- 거절은 공개 접수/쓰기/공급자 호출 이전이며 민감한 입력·ID를 로그/응답에 넣지 않습니다. 권한 오류는 예산을 소비하지 않습니다. 개인정보 삭제/관리 명령은 제한에서 제외하고 예산 초기화 수단으로 사용하지 않습니다.

### 실제 검증 증거

- 기존 baseline: **105 passed, 1 skipped**. 최초 실행의 `.runtime` 누락은 디렉터리 생성 뒤 해소했습니다(제품 결함이나 RED 증거로 계산하지 않음).
- RED→GREEN: 모듈 부재 → 사용자 속도 제한; 회전 사용자에 의한 서버 한도 우회 → 서버 예산; 중첩 요청 허용 → 사용자/서버/전체 동시 제한; 추적 상한 부재 → bounded 상태; 서버 창 만료 시 늦게 시작한 사용자 예산 고아화 → 서버 유지; 잘못된 설정 허용 → 엄격한 설정 검증; 제한 요청 공개 접수 발생 → 실제 두 명령의 입구 연결.
- 추가 RED→GREEN: 잘못된 admission 설정으로 client 생성 실패 시 SQLite가 열려 있던 문제 → `finally` 보호 범위 안으로 client 생성 이동.
- 전체 로컬 테스트: **143 passed, 1 skipped** (macOS Python 3.9.6; Linux `systemd-analyze` 없음). 새 테스트는 실제 SQLite/명령 콜백을 사용하고 Discord HTTP만 대체합니다. clock 주입으로 경계·만료·tenant 독립성을 검증했습니다.
- HTTP 3개 await 경계 × 두 명령 × 오류/취소, 공급자 취소/시간 초과/오류/개인정보 무효화 종료 뒤 재진입, 실패 시 속도 예산 비환불, 제한 중 개인정보 삭제, 기존 receipt race 회귀 검증 통과.
- `compileall`, `git diff --check`, 실제 CLI `run --check`: **6 commands; provider=disabled-codex; no network/login**.
- 원격 최종 SHA/PR/Ubuntu Python 3.11·3.12 CI는 push 후 정확한 head로 조회하여 PR 및 인계 증거에 별도로 기록합니다. 이 문서 자체는 원격 CI 통과를 미리 주장하지 않습니다.

### 구현과 운영의 경계

- 구현/로컬 검증 완료이지 배포/실서버 검증 완료가 아닙니다. 로그인, 실 Discord 호출, Codex transport 활성화, 서비스 배포를 하지 않았습니다.
- 단일 클라이언트/이벤트 루프의 in-memory 제한입니다. 고정 창 경계 burst, 재시작 초기화, 다중 서버 포화, 별도 부모 채널 공정성/분산 제한 부재를 명시합니다. 관리 명령/거절 안내 자체의 부하와 저장량·보존기간은 별도 후속 범위입니다.
- 불필요한 지식 수집/공급자 구현/외부 서비스 의존성/DB schema 변경 없음. 원격에는 비밀 없는 소스·테스트·이 문서만 저장합니다.
- **병합하지 않음**: 부모 에이전트의 독립 코드 검토 후 판단할 PR입니다.

## 후속 PR: tenant stored-case capacity (2026-10-14)

- 기반: PR #3 병합 `eaa39635fe7f553616140c6cccd0e2347eef1562`. 별도 `GPT-Discord-Bot-capacity` worktree / `feat/tenant-case-capacity` 브랜치. admission worktree는 변경하지 않았습니다.
- 최소 설계: tenant `(guild, parent_channel)`별 candidate + confirmed **합계** 상한. 기본 1000, `HELPER_CASES_PER_TENANT`로 1–100000 설정. 상태별 별도 한도/예약/마이그레이션 없이 승격은 기존 행을 유지합니다.
- 알려진 포화 상태는 공개 receipt와 admission 전에 거절. receipt 대기 중 경쟁은 `BEGIN IMMEDIATE`의 최종 활성 설정/합계 검사 및 사례+문맥 원자적 저장으로 차단. 예약이 아니므로 경쟁 중 이미 보낸 Discord embed는 되돌리지 않습니다.
- 기존 초과 행 보존, 자동 retention sweep 없음. 개인정보/관리/gateway 삭제는 quota와 독립이며 삭제 후 용량 재사용 가능. `/reset`은 사례 용량을 반환하지 않습니다.
- 물리 DB/디스크 상한이 아님: tenant 수 및 history 키 수 무제한, SQLite 페이지/저널/백업 별도. 자세한 한계와 운영 설정은 README에 명시했습니다.
- RED→GREEN 실제 관찰: 한도 초과 후보가 저장됨(1 failed) → 트랜잭션 quota; 잘못된 설정 허용/오류 원문 노출(9 failed) → 엄격한 설정 검증; full tenant의 공개 receipt 조회 발생(1 failed) → preflight 연결.
- 최종 로컬 전체: **175 passed, 1 skipped** (macOS Python 3.9.6, systemd parser 검사 skip). SQLite 동시 연결 Barrier 경쟁, rollback/lock 실패, lowered-limit 재시작, tenant/thread 격리, 삭제 후 재사용, 실제 callback receipt 경쟁/취소/정리와 기존 admission/privacy 회귀 포함.
- `compileall`, `git diff --check`, CLI doctor 및 설정값 500의 `run --check` 성공: 6 commands, disabled-codex, no network/login, credentials_present=False.
- 원격 최종 SHA/Ubuntu CI는 push 후 확인하고 PR/인계에 기록합니다. 이 문서가 CI 완료를 선행 주장하지 않습니다. 부모 독립 검토에 넘기며 **병합/배포하지 않습니다**. 인증 파일 접근, 공급자 활성화/유료 API 전환 없음.
