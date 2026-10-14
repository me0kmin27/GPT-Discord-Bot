# 릴리스 준비 체크리스트 — PR #2–#7 병합 후

기준: `me0kmin27/GPT-Discord-Bot`의 `origin/main`
`7f9f5ee6dd6b494ad2163b069e05a846d0c90061`. 이 문서는 **문서·테스트 전용 후속 PR**이며 배포 승인이 아니다.

## 판정 / 원래 목표와의 차이

원래 목표는 **API 키 없이 Codex를 쓰는 공개 Discord 도우미 + 사용자가 확정한 지식의 점진적 축적**이다.
최초 저장소 기록 `ff0f2ef:docs/PROGRESS.md`, 최초 README가 들어온 PR #2 및 현재 README를 대조했다.
최초 로컬 마일스톤은 의도적으로 공급자를 닫았다. 이것을 원래 생성형 도우미 목표 달성으로 바꾸어 해석하지 않는다.

- **구현·오프라인 검증됨:** 빈 지식 → 명시적 질문 후보 → 사용자 확정 → 관련 사례/출처 조회 → 로컬 개인정보 삭제.
- **CI fixture 검증됨:** Linux user-systemd 수명주기·실패 복구. 실제 봇 실행/Discord 연결은 아니다.
- **live 미검증:** Discord 로그인·초대·명령 동기화·실권한·삭제 이벤트·출처 링크 접근, 대상 서버 배포·비밀 복구.
- **차단:** Codex 생성 transport는 없다. 운영자 구독 하나를 app-server 인증으로 공개 호스팅 relay하는 경로는 진행하지 않는다. 승인된 대안 결정 없이 API 키/유료 공급자로 바꾸지 않는다.

`구현됨`은 소스 존재, `오프라인 검증됨`은 실제 실행한 로컬 경계,
`CI fixture 검증됨`은 아래 지정 환경만, `live 미검증`은 실제 운영 증거 없음,
`차단`은 선행 결정/허가 없이 진행 금지를 뜻한다. 완료율은 산출하지 않는다.

## 요구사항 ↔ 코드 ↔ 증거

| 요구사항 | 현재 코드 / 테스트 | 상태 및 남은 경계 |
|---|---|---|
| 지식 0건 시작, 수동 확정, 생성 답변 자동 학습 금지 | `Store.candidate/resolve`, `Service.ask`; `test_cases.py`, `test_release_acceptance.py` | 구현·오프라인 검증됨. 모델 학습/자동 수집 아님 |
| 서버·부모 채널 지식 격리 / 사용자·스레드 문맥 격리 | `Scope`, `Store.history/search_knowledge`, `scope_for`; `test_privacy.py`, `test_discord.py`, `test_retrieval.py` | 구현·오프라인 검증됨. Discord 권한은 HTTP 대역 기반, live 미검증 |
| 관련 확정 사례와 원래 해결 출처 | `Store.search_knowledge`, `Service.source_link`; `test_retrieval*.py` | 구현·오프라인 검증됨. 최근 ID 1000행/최대 3건의 어휘 검색, 의미 검색·정답 보증 아님 |
| 삭제 후 재노출 방지 | `Store.delete_user/delete_sources`, `operation`; `test_receipt_races.py`, `test_release_acceptance.py` | 로컬 DB 및 아직 제출하지 않은 응답 검증. 오프라인 이벤트 누락·이미 전송된 게시물·백업은 별도 |
| 요청/저장 상한 | `admission.py`, `Store.check_capacity/candidate`; `test_admission*.py`, `test_capacity*.py` | 단일 프로세스 구현·오프라인 검증됨. 전체 디스크/tenant 수/history 키 수 상한은 아님 |
| Linux 운영 CLI | `manage.py`; `test_manage*.py`, `test_systemd.py`, `systemd_lifecycle.py` | 오프라인 및 실제 CI fixture 검증됨. 실제 봇 ExecStart/토큰/재부팅·linger/복구는 미검증 |
| API 키 없는 Codex 생성 | `DisabledCodex.answer`, `create_client` | **미구현·차단**. 로그인 위임 도구는 transport/호스팅 허가가 아님 |

## 오래된 마일스톤 기록의 정정

`PROGRESS.md`와 `VERIFICATION.md`의 아래쪽 수치·“병합 안 함/CI 대기”는 **작성 당시 기록**이다.
현재 상태로 읽지 않는다. PR #2–#7은 모두 MERGED로 원격 재조회했다.
각 PR 댓글의 독립 검토는 해당 head/선언 범위에 한하며 공개 서비스 전체 승인이 아니다.

| PR / 범위 | 최종 PR head | main 병합 commit |
|---|---|---|
| #2 코어/Discord/CLI 및 receipt race | `eda4ba45b277528fa84a39a883adbbb39ff730e8` | `4faee3042f02df8679fd3c388ab1fd0ac61e59e6` |
| #3 admission | `ed9f748a6a5d1f56c53caae28ec5f3416d5da0cd` | `eaa39635fe7f553616140c6cccd0e2347eef1562` |
| #4 사례 capacity | `1d86776eec9344c5b1c19224443014b25a377cc1` | `18e0fbc6ea06ece4042ef7a6120ad81c5abffbb1` |
| #5 Linux fixture | `11e9f1b604e1a4e2ab370b62c9c09de0cef94a9b` | `ef631d7cd1188384079f1571ab944b7e5dc12499` |
| #6 fixture cleanup | `7a95c960a78c0f3ceb1999414ec36b5b4ad1bf57` | `21afcfc00ecc9913984c697f9c94e54b0f4eaf23` |
| #7 관련 사례 검색 | `d04ac8028b68872e980162dd5836c7e7a5035e26` | `7f9f5ee6dd6b494ad2163b069e05a846d0c90061` |

현재 병합 main의 Actions run **38556271591**은 `headSha`가 위 기준 SHA와 일치하며,
Python 3.11/3.12, systemd normal/failure-recovery 네 job 모두 성공으로 재조회했다.
PR head, GitHub의 PR synthetic merge, 실제 main squash commit은 서로 다른 식별자다.
예전 50/105/143/175/190 테스트 수는 해당 시점 기록이지 현재 총수가 아니다.

## 재현 가능한 오프라인 acceptance

README 설치 절차로 테스트 의존성을 설치한 뒤 저장소 루트에서:

```bash
mkdir -p .runtime
.venv/bin/python -m pytest -q tests/test_release_acceptance.py --basetemp=.runtime/smoke
.venv/bin/python -m pytest -q --basetemp=.runtime/pytest
.venv/bin/python -m compileall -q helperbot tests
```

`test_question_confirm_retrieve_privacy_delete_persists`는 실제 `Service`, `Store`, 파일 SQLite,
실제 `DisabledCodex`를 사용한다. 질문/해결 message ID와 입력은 합성 자료다.

1. 빈 DB에 명시적 채널 참여 → `Service.ask` 후보 저장, 확정 전 검색 제외.
2. `Store.resolve`로 직접 작성한 해결 확정.
3. 더 최신인 무관 사례와 같은 질문의 다른 서버 사례를 추가.
4. 형제 공개 스레드를 표현하는 Scope의 다른 사용자 질문 → 관련 원본 한 건만 조회, 원래 해결 링크/비생성 안내 확인.
5. `/privacy_delete`가 호출하는 `Store.delete_user` 실행 → 본인 사례/문맥 삭제.
6. 재질문에서 삭제된 해결·링크가 사라지고 무관 사례/다른 서버 자료는 보존됨을 확인.
7. SQLite 파일을 닫고 다시 열어 삭제 지속성과 다른 서버 보존을 확인.

기존 개별 테스트를 대체하지 않는 한 개의 연결된 acceptance이다. Discord HTTP/권한/명령 dispatch,
admission, 실제 출처 링크 존재/접근성은 이 테스트의 증거가 아니다. 의존성 설치에는 네트워크가 필요할 수 있으나
**이 시나리오 자체는 로그인·네트워크·모델 호출 없이 실행**한다.

실행 증거: 병합 main baseline **222 passed, 1 skipped**; 추가 후 전체 결과는 VERIFICATION 상단 참조.
새 테스트는 기존 동작의 characterization이며 production 수정/새 기능의 TDD RED라고 주장하지 않는다.
삭제를 프로세스 안에서 no-op으로 바꾼 음성 대조 실행은 `history(owner) == []`에서 **1 failed**를 관찰했다.
소스 파일은 변경하지 않았으며 정상 구현으로 재실행한다. 실제 삭제 결함을 발견했다는 뜻이 아니다.

## 공급자 결정 — 현재 요구와 이전 검토 기록

**2026-10-14 후속 정정:** 사용자는 **Codex login OAuth 유지 및 구현**을 확정했다.
아래 A/B/C는 이전 의사결정 시점의 기록이며 인증 방식을 다시 선택하라는 요청이 아니다.
[Codex OAuth 기술·운영 조건 조사](CODEX_OAUTH_DECISION.md)에 공식 연결 계약, 제한 문구의 정확한 범위,
무도구 검증 항목 및 SIWC와의 차이를 기록했다. 로그인·배포 없이 transport 구현/오프라인 검증은 진행한다.
공개 호스팅 조건 확인과 실제 로그인·모델·Discord·배포 검증은 별도 gate다.
SIWC/API 키/다른 공급자로 묵시 전환하지 않는다. 아래 ‘선택 전’ 문구는 과거 상태로 읽는다.

공식 Codex app-server 문서의 **Auth endpoints**는 다음과 같이 명시한다:
“App-server authentication has never been permitted for commercial or hosted services.”
공식 문서를 이번 대조에서 다시 읽었으며 단순히 ‘조건을 아직 찾아보지 않음’ 상태와 구별한다.
로컬/오픈소스 앱에 대한 설명을 모든 공개 호스팅 허가로 확대하지 않는다.

공식 근거 (검토 시점 2026-10-14, 활성화 전 재확인):
- `https://developers.openai.com/codex/app-server` (현재 공식 ChatGPT Learn 문서로 이동), Auth endpoints
- `https://developers.openai.com/siwc` — 별도 Sign in with ChatGPT 경로. 이 Discord 구성의 허가를 확인했다는 뜻은 아님.

운영자가 결정할 선택지:
- **A. 생성 없이 제한된 사례 검색 pilot 먼저:** 원래 생성형 목표는 미달임을 인정하고 disabled provider 유지. Codex 로그인 불필요. 아래 Discord/배포 gates는 여전히 필요.
- **B. API 키 없는 원래 목표 유지:** 이 공개 Discord 서비스에 적용 가능한 공식 이용자별 인증/앱 승인 경로 확인을 승인할지 결정. 허가 확인 → 별도 보안 설계/무도구 강제/tenant·사용자·스레드 격리/삭제 검증 → transport 구현·검토 순서. 단일 운영자 구독 relay는 선택지 아님.
- **C. API 기반 재설계 검토:** 사용자만 기존 ‘API 키 없음’ 조건 변경과 비용/한도를 명시적으로 승인할 수 있다. 이 PR은 전환/결제/구현하지 않는다.

B/C는 자동으로 시작할 기능 backlog가 아니다. 선택·정책 허가·별도 범위 승인이 먼저다.
프롬프트의 도구 금지 문구, read-only, 로그인 성공을 실제 zero-tools 및 호스팅 허가의 대용으로 삼지 않는다.

## 유한한 남은 release gates

| Gate | 완료 판정 / 필요한 결정 | 지금 사용자 결정 없이 진행 가능한가 |
|---|---|---|
| G1 저장소 인계 | 이 docs/test PR 정확한 head의 전체 테스트·CI·독립 검토, 원격 head 일치. **이 작업은 병합하지 않음** | 테스트·CI·검토 가능. 완료 후 주변 기능 추가 대신 인계 |
| G2 제품/공급자 | A/B/C 선택. B/C는 공식 허가·보안 계약·별도 구현 검토 없이는 생성 활성화 불가 | 선택 전 문서/기존 회귀 검증만 가능 |
| G3 Discord pilot | 앱/테스트 guild ID, 부모 텍스트 채널/공개 스레드, 관리자·일반·메시지관리 테스트 역할, 초대·명령 등록 권한 및 시험 동의 | 대상 지정/승인 필요. 토큰은 채팅에 받지 않음 |
| G4 실행 대상 | Linux 호스트 식별, 전용 비-root 계정, Python/경로, 단일 인스턴스, foreground pilot 또는 user-systemd, 전역 sync 허용 여부, enable/linger 여부, 실행·중지 권한 | 대상·운영 변경 승인 필요. 현재 기본 unit은 guild-only sync 옵션 없음 |
| G5 live acceptance | G3/G4 승인 후 아래 절차를 실제 실행하고 SHA/시간/비민감 결과 기록 | 대상 승인 전 실행 불가. disabled provider로도 가능 |
| G6 운영/공개 승인 | pilot 규모/접근 범위, 보존·디스크 경보·백업/복구·삭제 누락 대응 담당자/절차 승인; 실제 복구 시험 및 중지/롤백 확인 | 절차 초안 검토 가능, 보존기간/자동삭제·인프라 구현은 임의 결정 금지 |

G3/G4에서 필요한 것은 **ID·대상·권한·운영 방식 결정**이다. Discord 토큰, OAuth 코드,
비밀번호, 인증 파일은 요청/공유하지 않는다. 승인 후 운영자가 대상 호스트의 숨김 입력/안전한 비밀 주입으로 설정한다.
기존 개인 Codex/Hermes 인증을 읽거나 복사하지 않는다.

### G5 live acceptance 실행 체크리스트 (현재 전부 미실행)

- [ ] 승인된 SHA와 provider=disabled 확인, 테스트 앱만 초대, 최소 권한/특권 intent 미사용 확인.
- [ ] foreground `run --sync-guild <승인된 guild ID>`로 테스트 서버 동기화. 기본 unit을 쓰면 전역 sync임을 먼저 승인받는다.
- [ ] 기본 비활성 거절 → 관리자 참여 → 질문 후보 → 다른 일반 사용자의 확정 거절 → 원 질문자/허용 moderator 확정.
- [ ] 공개 형제 스레드에서 관련 사례/해결 링크 접근, 다른 부모 채널/서버·DM·비공개 스레드 경계 확인.
- [ ] 권한 회수 후 거절, 멘션 무알림, 상한 거절 뒤 개인정보 삭제 명령 사용 가능 확인.
- [ ] 개인정보 삭제/접수 메시지 삭제/채널·스레드 삭제 후 DB·재검색 확인. 이미 게시한 메시지는 별도 수동 정리.
- [ ] 승인 대상의 실제 봇 시작/상태/재시작/중지 및 비밀 비노출 확인. 부팅/로그아웃 지속성은 선택한 운영 정책대로 별도 시험.
- [ ] 서비스 중지 후 합성 DB 백업/복구 시험, 삭제 데이터가 오래된 백업에서 재공개되지 않도록 절차 확인. 실데이터/비밀은 Git에 올리지 않음.

## 범위 내 correctness 검토 결과 / 남은 위험

이번 대조에서 Store/Service/provider/Discord callback의 실제 병합 코드를 읽고 기존 회귀를 실행했다.
**새로운 production correctness 결함은 확인하지 않았다.** 문서의 과거 병합/CI 대기 표현과 연결된 acceptance 증거 부족을 이 PR에서 정리한다.
이는 전체 보안 감사/모든 결함 부재 보증이 아니다. 독립 최종 검토는 G1로 남긴다.

공개 준비를 막는 구체적 미충족은 생성 transport/허가 부재, live Discord·대상 운영 미검증이다.
이미 알려진 한계는 단일 프로세스 취소/admission, 전체 저장량·문맥 키 수/보존기간 상한 부재,
오프라인 삭제 누락, 이미 게시한 Discord/외부 백업의 삭제 비보장, lexical 오탐/누락·고정 검색 창이다.
G6에서 제한된 pilot의 수동 통제와 잔여 위험 수용 여부를 결정한다. 무제한 공개 서비스 준비 완료로 표시하지 않는다.
벡터 검색/자동 학습/대시보드/분산화 등 주변 기능을 이 체크리스트 완료를 위한 필수 새 작업으로 만들지 않는다.
