# Codex login OAuth transport 구현 / 활성화 gate

확정 인증 방식은 **Codex login OAuth**다. SIWC/API 키/다른 공급자로 바꾸지 않았다.
이 문서는 `CODEX_OAUTH_DECISION.md`의 공식 이용조건 조사와 별도로 **실제 구현·실행 증거**를 기록한다.

## 구현 상태

- `helperbot/codex_transport.py`의 `CodexOAuthProvider`는 공식 managed-auth stdio 경로를 구현한다:
  `initialize` → `initialized` → `account/read(refreshToken:false)` → 새 `thread/start` →
  `turn/start` → JSONL delta/item/terminal 이벤트 검증 → `ProviderReply`.
- OAuth 토큰·갱신 endpoint를 직접 구현하거나 인증 파일을 읽지 않는다. 공식 Codex 프로세스가
  전용 `CODEX_HOME`의 로그인을 관리한다. 기존 `codex-login`의 `<data>/codex`와 같은 경로다.
  `cli_auth_credentials_store="file"`, `forced_login_method="chatgpt"`를 명시하며 API-key account는 거절한다.
- `answer()` 첫 단계의 **고정 readiness gate가 프로세스 생성·파일 생성 전에 거절**한다.
  환경 변수/CLI 옵션으로 해제할 수 없다. Discord `create_client`/관리 CLI는 계속 `DisabledCodex`다.
  구현된 하위 경로는 테스트에서만 gate 함수를 대체하고 **실제 subprocess fixture**를 연결하여 실행한다.
  소스 패치/테스트 monkeypatch는 활성화 기능이 아니며 운영 사용법으로 제공하지 않는다.
- **구현 완료 ≠ 로그인된 생성 검증 ≠ 공개 호스팅 승인 ≠ 배포 완료.** 실제 생성은 아직 열지 않는다.

## 제품 경로 검증과 남은 저장 gap

최종 목표는 **관련 해결 사례를 활용하고, 없으면 Codex OAuth로 새 답변을 생성**하는 도우미다.
현재 비생성 검색 fallback은 미완성 상태의 안전한 임시 동작이지 제품 요구의 대체가 아니다.
`test_no_match_generates_candidate_then_manual_resolution_is_retrieved`는 실제 Service/SQLite/stdio fixture로
빈 사례 → provider 호출/생성 형식 응답 → candidate ID와 답변 연결 → 사용자가 `/resolved`에 해당하는
수동 해결 확정 → 다음 요청에서 해당 사례 검색/인용을 검증한다. 생성 답변은 자동 확정하지 않는다.
이 테스트는 live GPT 검증이 아니며, 실제 봇에서는 고정 gate 때문에 생성이 아직 불가능하다.

**별도 구현 gap:** 현재 DB candidate에는 질문과 receipt가 저장되고 생성 답변 본문은 `Answer.text`/Discord
응답에만 연결된다. 생성 답변 원문을 candidate의 영속 필드로 보관하는 스키마/삭제/보존 계약은 이 transport
PR에서 추가하지 않았다. 따라서 ‘질문·AI답변 쌍을 후보로 영속 축적’까지 완료했다고 주장하지 않는다.
향후 해당 저장 계약을 구현하더라도 사용자 해결 확인 전 검색 가능한 confirmed 지식으로 승격하지 않아야 한다.

## 실제 코드의 경계

1. 요청마다 새 프로세스, 빈 HOME/작업 디렉터리, fresh ephemeral thread다. resume/fork/steer나 tenant별
   thread 캐시는 없다. 요청 종료 후 임시 디렉터리를 정리한다. `CODEX_HOME`만 앱 인증 경로로 고정한다.
   전달 환경은 HOME/CODEX_HOME/PATH(시스템 기본 검색 경로)/LANG/TMPDIR뿐이다.
   Discord 토큰, API 키, proxy/개인 환경 변수, 부모 cwd는 전달하지 않는다.
2. 질문/이력/사례는 JSON 자료로만, 지시문은 `developerInstructions`로 분리한다.
   사례의 id/question/solution만 전송 대상으로 선택하며 작성자·guild·출처 message 메타데이터는 제외한다.
   요청별 입력 제한은 질문/각 이력/각 사례 문장 2000자, 이력 8개, 사례 3개, 지시문 4096자,
   직렬화된 자료+지시문 UTF-8 48 KiB다. 부적합 입력은 프로세스/파일 생성 전 거절한다.
3. 수신 frame 64 KiB, 총 수신 1 MiB, 메시지 2048개, 응답 대기 알림 queue 64개다.
   assistant item 32개, item당 8 KiB, 누적 delta 32 KiB를 제한한다.
   최종 출력은 JSON의 text(비어 있지 않은 최대 1000자)/case_ids(제공된 실제 사례 ID 최대 3개)만 허용한다.
   boolean ID·추가 필드·알 수 없는 출처·delta/완료 text 불일치·중복 최종 답변은 거절한다.
4. thread/turn 응답 ID와 이벤트 범위를 검사한다. `turn/completed.status=completed`, error 없음,
   final_answer item 검증 전에는 부분 텍스트를 Discord에 보내지 않는다.
   알 수 없는 notification, malformed/EOF/oversize, RPC error는 민감 내용을 포함하지 않은 고정 오류로 처리한다.
5. **모든 서버→클라이언트 request**(approval, dynamic tools, 외부 token refresh, 미지의 새 RPC 포함)를
   JSON-RPC error로 거절하고 요청을 실패시킨다. userMessage/reasoning/agentMessage 이외 item은 거절한다.
   read-only/approvalPolicy=untrusted는 보조 방어일 뿐이다. 알림을 보고 중단하는 것은 이미 실행된
   built-in tool의 사전 차단을 증명하지 않으며, 이 때문에 readiness gate를 닫아 둔다.
6. 기본 전체 요청/프로토콜 deadline 20초. 내부 제한을 넘어 서비스의 wait_for/task cancellation도 전달된다.
   종료/실패/취소 시 POSIX 프로세스 그룹을 SIGKILL하고 직접 자식을 reap한다. spawn 도중 취소에도
   생성된 child handle을 회수하며, 정리 중 재취소가 성공 답변으로 바뀌지 않게 검사한다.
   일반 `turn/interrupt`의 원격 확인에 기대지 않는다. OS spawn/reap 자체가 고장 난 경우의 하드 실시간
   종료 보장은 없으며, 새 session으로 탈출한 악성 자식/호스트 SIGKILL까지 해결하는 컨테이너 보안 경계는 아니다.
7. 애플리케이션은 요청/응답/인증/서버 오류 본문을 로그에 남기지 않고 child stderr를 DEVNULL로 보낸다.
   이것은 **Codex 내부 파일/텔레메트리 또는 원격 보존 없음**의 보증이 아니다.
   앱 `CODEX_HOME`의 기존 config/skills/MCP/hooks/plugin과 시스템 config 전체의 불변 격리는 아직
   검증하지 않았다. 빈 cwd/환경 allowlist만으로 동일 UID의 파일 접근이 막히지도 않는다.
8. 기존 Service/Store pending 무효화와 receipt/admission 경계를 변경하지 않았다.
   실제 Store+Service+프로토콜 fixture로 삭제/reset/disable 뒤 늦은 결과 폐기, task 취소 뒤 reap을 검증한다.
   Store privacy 무효화는 이미 전송한 외부 요청 자체를 소급 취소하지 않으며 서비스의 결과 게시를 막는다.

## 정확한 zero-tools 미충족 항목

검증 대상은 공식 `@openai/codex@0.162.1`이고, tag `rust-v0.162.1`이 가리키는 commit은
`092d3acd6bec3e3a14bdc7e7a2810ab628ab759d`다. 이동하는 main이나 다른 설치본과 혼동하지 않는다.

- 실제 바이너리가 생성한 stable `ThreadStartParams`/`TurnStartParams`에는 전역
  tools/toolChoice/tool_choice/allowedTools 필드가 없다. 임의 `config` map이 허용된다고
  이름을 추측한 `allowed_tools=[]`를 넣어 강제된다고 주장하지 않는다.
- 같은 tag의 `ToolPolicy.allowed_tools=Some(empty)`는 내부 엔진의 deny-all 정책이고,
  `ToolRegistry` 등록 경로가 이를 검사한다. 그러나 이는 thread 시작 전 `ExtensionDataInit`로
  제공하는 Rust embedding 경계다. 이번 지원된 JSON-RPC 경로에서 설정하고 적용을 증명하지 못했다.
- `features.shell_tool`, multi_agent/apps/hooks, web_search/MCP의 개별 제어는 별도 방어다.
  shell만 끄면 도구 전체가 사라지는 것은 아니다. 예를 들어 pinned `spec_plan.rs`는
  `update_plan_enabled` 조건의 PlanHandler를 별도 등록한다.
  이 구현은 토글 조합을 **검증된 빈 도구 registry라고 오인하여 활성화하지 않는다**.
- 따라서 정확히 남은 것은 **지원되는 공식 transport에서 모든 built-in/hosted/dynamic 도구의
  광고 목록과 실행 registry를 사전에 빈 상태로 강제하고 검증할 경로**다.
  스키마의 특정 필드 부재만으로 엔진 전체에서 영원히 불가능하다고 단정하지 않는다.
  커스텀 Codex 빌드, 비공개 endpoint, ChatGPT 웹 scraping으로 우회하지 않았다.

## 실제 공식 바이너리 probe (인증 없이)

`tools/protocol/package.json` + lockfile은 공식 npm 패키지 **0.162.1**과 integrity를 고정한다.
전역 설치/개인 Codex 실행 파일을 쓰지 않는다. node shim은 최소 PATH에서 Node를 못 찾을 수 있어
설치된 platform package의 **native executable**을 정확히 하나 찾는다.

```bash
npm ci --prefix tools/protocol --ignore-scripts --no-audit --no-fund
mkdir -p .runtime
.venv/bin/python tests/probe_codex.py tools/protocol/node_modules .runtime
```

probe는 매번 새로운 HOME/CODEX_HOME/cwd를 만들고 version 확인 및 JSON schema 생성 후,
실제 stdio initialize/initialized/account-read를 수행한다. thread/start, turn/start, login을 호출하지 않는다.
새 home이 signed-out이고 auth.json이 생성되지 않았으며 직접 자식이 종료됐음을 확인한다.
개인 `~/.codex`/Hermes auth 파일을 읽거나 복사하지 않는다.

2026-10-14 macOS ARM64 실제 결과:

```json
{
  "binary": "codex-cli 0.162.1",
  "initialize": "ok",
  "initialized": "sent",
  "account": "signed-out",
  "auth_file_created": false,
  "thread_or_turn_started": false,
  "process_reaped": true,
  "live_inference": false,
  "zero_tools_verified": false
}
```

실제 초기 알림 `remoteControl/status/changed`도 관측했다. status=disabled만 허용하며
connected/알 수 없는 상태는 거절한다. remote control을 켜거나 WebSocket을 열지 않았다.
Linux CI 초기 probe에서는 공식 `configWarning` 알림 때문에 실패했다. 이후 warning 본문은 버리고
존재 여부만 기록하도록 구분했다. **initialize/account-read 진단만 계속할 수 있고 thread/start 등
추론 관련 RPC는 거절**한다. 추론 중 도착한 warning도 즉시 실패한다. 경고를 숨겨 live readiness로
바꾸거나 설정 검사를 우회하지 않는다. probe 결과의 `configuration_warning_observed`를 함께 확인한다.

생성 스키마 SHA-256은 pinned GitHub 소스 파일의 SHA-256과 일치했다:

| 파일 | SHA-256 |
|---|---|
| ThreadStartParams | `e9c6d3cc18d049bfbc0249add3808fb8e5a27e1a0b5a423767aafbc3859a9428` |
| TurnStartParams | `583aff13e7a2da43fbb0150e0edc3c73171f374f0aa745dddba256166988a005` |
| GetAccountParams | `30b545275f60975b55bd6fbaafd70f15505801d14168ee82d3931b6e93c78aab` |

로컬 Python 3.9 회귀 실행: **276 passed, 1 skipped** (Linux 전용 항목), compileall 및 diff whitespace 검사 통과.
CI `codex-protocol` job은 Ubuntu에서 같은 공식 바이너리 probe를 실행한다.
기존 Linux Python 3.11/3.12 전체 회귀 및 systemd 정상/실패복구 jobs도 유지한다.
fixture의 합성 답변은 **live 모델 성공 증거가 아니다**. 실제 account/read 성공도 추론 성공이 아니다.

## 남은 실제 인증/추론 gate

1. 지원된 no-tools 강제와 개인 config/credentials/host 파일 접근 격리의 검증, 독립 코드 검토.
2. 사용자에게 **앱 전용 새 로그인 및 그 인증을 사용한 제한된 live 추론**의 명시적 허가를 받은 뒤에만
   기존 공식 `codex-login`을 사용한다. 지금은 로그인·기존 인증 접근·추론 모두 실행하지 않았다.
3. 허가된 계정으로 managed-auth 상태/만료·갱신·실패, 실제 모델의 schema/stream/terminal 응답,
   취소/삭제 경계를 검증해야 한다. 지금은 이 항목을 fixture로 대체하여 완료했다고 주장하지 않는다.
4. 공개 hosted 운영은 공식 제한에 대한 적용 가능한 허가를 별도로 확인해야 한다.
   로컬 OSS transport 구현을 금지한다는 뜻도, OAuth 요구를 재선택하라는 뜻도 아니다.
   Discord 테스트 서버/운영 배포 역시 별도 승인·검증 대상이다.

## Primary sources

- 공식 app-server 문서: https://learn.chatgpt.com/docs/app-server
- 공식 Codex auth: https://developers.openai.com/codex/auth
- pinned schema: https://github.com/openai/codex/tree/092d3acd6bec3e3a14bdc7e7a2810ab628ab759d/codex-rs/app-server-protocol/schema/json
- pinned ToolPolicy: https://github.com/openai/codex/blob/092d3acd6bec3e3a14bdc7e7a2810ab628ab759d/codex-rs/ext/extension-api/src/tool_policy.rs
- pinned registry: https://github.com/openai/codex/blob/092d3acd6bec3e3a14bdc7e7a2810ab628ab759d/codex-rs/core/src/tools/registry.rs
- pinned tool plan: https://github.com/openai/codex/blob/092d3acd6bec3e3a14bdc7e7a2810ab628ab759d/codex-rs/core/src/tools/spec_plan.rs

문서의 일반 OAuth/hosted 정책 해석은 [공식 조사](CODEX_OAUTH_DECISION.md)의 범위를 따른다.
위 pinned source와 배포 binary/schema는 이번 구현에서 직접 확인했다.
