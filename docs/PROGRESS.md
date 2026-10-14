# 로컬 첫 마일스톤

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
