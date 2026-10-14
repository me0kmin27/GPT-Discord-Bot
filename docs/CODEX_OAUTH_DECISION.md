# Codex login OAuth: 기술 연결과 공개 서비스 조건의 분리

조회일: **2026-10-14 KST** (`date -Iseconds`: 2026-10-14T20:46:15+09:00).
기준 소스: `me0kmin27/GPT-Discord-Bot` main `d244c360aa894cb0fc1f8269f5576b6c431e7595`.
이 문서는 해당 기준의 조사 결과이며 이후 구현 PR의 상태를 대신하지 않는다.

## 확정 요구와 결론

- **확정 요구는 Codex login OAuth**다. SIWC, API 키, 다른 공급자로 대체하거나 인증 재선택을 요구하지 않는다.
- Codex CLI의 ChatGPT 로그인 및 app-server의 managed ChatGPT 인증/대화 RPC는 공식 문서에 존재한다. OAuth 자체가 기술적으로 불가능하거나 전면 금지라는 결론은 잘못이다.[18][15]
- 반면 app-server **인증** 문서는 commercial 또는 hosted services에 명시적 제한을 둔다. 이 공개 Discord 서비스에 대한 예외 허가나 운영자 구독의 다중 사용자 relay 허용은 이번 공식 문서 조사로 확인되지 않았다.[15]
- **진행 가능:** 사용자 승인 범위의 transport 구현, 오프라인 가짜 subprocess/RPC 테스트, 격리·취소·무도구 검증 설계. **별도 미충족:** 실제 로그인/인증 접근 승인, 라이브 추론 검증, 공개 호스팅 이용조건 확인, Discord 배포 승인. 이용조건 미확인이 안전한 오프라인 구현을 중지시키는 이유는 아니다.
- 이번 문서 작업은 production/transport를 수정하지 않는다. 다른 구현 worker와 파일 범위를 분리한다. 기존 인증 읽기·복사, 로그인, 모델 요청, 신청 제출, 배포를 실행하지 않았다.

## 1. 실제 공식 연결 계약

### Codex가 OAuth를 소유하는 경로

CLI는 `codex login`의 브라우저 흐름 및 `codex login --device-auth`를 문서화한다. 후자는 계정/워크스페이스의 device-code 사용 설정이 필요하며 beta다. Codex가 저장된 ChatGPT 세션의 갱신을 관리한다.[18]

app-server는 기본 stdio JSONL을 제공한다. 통합 클라이언트는 `initialize` → `initialized` 후 `account/read`로 상태를 확인하고, 필요 시 별도 사용자 승인 하에 `account/login/start`의 `chatgpt` 또는 `chatgptDeviceCode`를 사용할 수 있다. 로그인 완료 알림과 account 상태 확인은 실제 모델 응답 완료와 다르다.[15]

대화 연결은 `thread/start` → `turn/start` → 응답 이벤트 처리다. `thread/resume`는 기존 대화를 이어가며, `turn/completed`의 상태가 성공인지 확인해야 한다. 모델 목록이나 로그인 성공만으로 추론 성공을 선언하지 않는다.[15]

이 계약을 이용해 **Codex가 인증을 관리하도록** 구현한다. 이 보고서는 Codex OAuth 토큰을 직접 읽어 일반 Responses API에 전달하는 계약을 확인하지 않았다. 아래 SIWC의 Responses 계약을 기존 Codex 로그인 토큰에 그대로 적용하지 않는다.[15][18]

### 토큰·scope 경계

Codex 공식 로그인 경로는 통합 코드가 OAuth scope나 refresh token을 직접 조작할 필요가 없는 managed 경로다. `CODEX_HOME`, credential store, 강제 ChatGPT 로그인 설정이 문서화되어 있다. 인증 저장소는 비밀이며 보고서/로그/Git/Discord 메시지에 포함하지 않는다.[18]

`chatgptAuthTokens`는 별도의 **experimental** 모드다. host가 이미 사용자 인증 수명주기를 소유해야 하며 `accessToken`, `chatgptAccountId`, 선택적 plan 정보를 제공한다. `account/chatgptAuthTokens/refresh` 요청 처리 책임도 host에 있다. 이 RPC의 존재는 토큰 취득 자격이나 공개 호스팅 허가를 부여하지 않는다.[15]

**구현 원칙:** 현재 요구에는 managed Codex OAuth만 사용하고, 기존 개인 세션 가져오기/토큰 전달 모드/다른 앱 client ID 사용을 도입하지 않는다. 본 조사에서 Codex 로그인에 적용할 제3자 앱용 public scope 등록 계약은 확립하지 못했다.

## 2. 제한 원문의 정확한 적용 범위

공식 app-server 문서 **Auth endpoints**의 원문:

> App-server authentication has never been permitted for commercial or hosted services.[15]

같은 단락은 local 또는 open-source application의 기존 사용을 계속할 수 있다고 설명하고 SIWC로 이동을 권고하며, commercial/hosted 용도를 지원하기 위해 SIWC를 출시했다는 설명과 partner waitlist 링크를 제공한다.[15]

따라서:

| 구분 | 판정 |
|---|---|
| 개인 로컬 Codex login OAuth | 공식 지원 문서 있음. 본 작업에서 라이브 시험은 안 함.[18] |
| 로컬/OSS app-server 통합 | 계속 사용 가능하다는 공식 설명 있음.[15] |
| 중앙 호스팅 공개 Discord + app-server 인증 | 제한 문구의 hosted service 범위에 해당한다고 판단. 예외/승인 확인 안 됨.[15] |
| 운영자 한 명의 구독을 다수 요청에 사용 | 로그인 기술은 존재하지만 이 relay의 이용 허가를 확인하지 못함. 사용량·권한 주체도 운영자에 집중됨.[15][18] |
| 각 사용자의 Codex OAuth를 중앙 서버에 연결 | 사용자별 인증만으로 hosted 제한이 없어지는 근거 없음.[15] |
| CLI로 프로세스만 바꾸기 | 위 문구는 app-server authentication에 관한 것이므로 모든 OAuth의 금지로 확대하지 않음. 그러나 CLI 문서도 public/untrusted 환경에 실행을 노출하지 말라고 경고하므로 공개 relay 우회 허가로 읽지 않음.[18] |

**불명확성:** 무료 비상업 OSS Discord 서비스, 특정 사용자만 접근하는 개인 self-hosted bot, 답변을 다른 사람이 보는 공동 채널이 각각 어떤 계약 범주인지 공급자의 서면 확인이 필요하다. 안전한 OS 격리는 이용조건의 예외 승인이 아니다. 반대로 이 운영 경계만으로 Codex OAuth transport의 오프라인 개발까지 금지라고 주장하지 않는다.

## 3. 격리와 zero-tools: 가능한 방어와 아직 증명되지 않은 것

공식 설정에는 `features.shell_tool`, `features.multi_agent`, `features.apps`, `features.hooks`, `web_search`, MCP enable 설정 등이 있다. shell 실행은 기본 활성이고 web search에는 명시적 `disabled`가 있다.[20]

read-only sandbox는 쓰기 제한이지 도구 제거가 아니다. sandbox가 허용하는 명령은 실행·읽기를 할 수 있으며 `approval_policy`는 승인 시점을 제어한다. `never`를 ‘모든 도구 금지’로 해석하지 않는다.[21][20]

**권고 설계(미실행, 해당 버전 검증 전 보장 아님):**

1. 독립 비-root 계정/프로세스, 비어 있는 작업 디렉터리, 전용 `CODEX_HOME`, 제한된 환경변수, personal config/skills/MCP/plugins/hook 미상속. 봇 토큰·DB·다른 tenant 자료는 모델 실행 프로세스의 읽기 경계 밖에 둔다.
2. stdio만 사용하고 app-server RPC를 인터넷에 노출하지 않는다. 공식 문서는 WebSocket이 experimental/unsupported이고 비-loopback 기본 연결의 인증 위험을 설명한다.[15]
3. 명령 도구/다중 agent/apps/hooks 비활성, web search disabled, MCP·dynamic tools 없음, read-only 및 낮은 수준 OS 접근/egress 제한을 함께 사용한다. 이 토글 목록만으로 모든 내장 도구가 제거되었다고 보증하지 않는다.[20][21]
4. 정확한 Codex 버전/생성 스키마/실제 도구 집합을 고정 검사하고 미지원 옵션이나 추가 도구는 fail closed. 이미 실행된 도구 알림을 보고 취소하는 것은 **사전 무도구 강제의 증거가 아니다**.
5. shell/read/patch/web/MCP/apps/subagent/동적 도구 각각에 대해 공격 입력을 주어 실제 실행 없음과 filesystem/network side effect 없음을 검증한다. 응답은 text-only allowlist, 알 수 없는 RPC 요청 거절, 제한 시간·출력 크기·취소·subprocess 종료·민감 오류 차단을 테스트한다.
6. tenant/user/thread별 문맥 소유권을 봇이 강제한다. app-server thread ID는 Discord 권한이 아니다. 삭제·취소 경합 및 재시작 시 history/rollout 삭제도 별도 검증한다.

**정확한 기술 미충족:** 기준 main에는 생성 transport가 없고, 이번 문서 작업은 로그인된 실제 CLI/app-server 연결, OAuth 갱신, 모델 응답, 버전별 zero-tools를 검증하지 않았다. 공식 문서에서 범용 단일 ‘모든 도구 제거’ 스위치의 보증도 확립하지 못했다. 다른 worker의 구현 결과와 해당 head의 테스트가 이 상태를 갱신해야 한다.

## 4. SIWC 조사 기록 — 요구 대체안이 아님

초기 조사 범위의 결과를 보존한다. **아래 내용은 Codex login OAuth 구현을 SIWC로 변경하라는 제안이 아니다.**

| 질문 | 공식 문서로 확인한 내용 |
|---|---|
| 일반 앱 등록 | client ID 요청 페이지는 selected commercial partners 및 interest-form waitlist를 명시한다. 즉 공개 문서가 있다고 모든 hosted 앱이 즉시 승인된 것은 아니다.[2] |
| OSS 경로 | quickstart는 모든 open-source partners와 selected private clients의 plan usage를 설명한다. 별도 overview는 OSS/locally hosted 범위이며 paid/remotely hosted 앱은 interest form으로 안내한다. OSS 저장소라는 이유만으로 중앙 hosted 자격을 확정하지 않는다.[14][3] |
| 사용자별 동적 등록 | `dynamic_agent_client`는 최초 등록 진입점이며 발급된 `client_id`를 저장·재사용한다. loopback callback, state/nonce/PKCE S256 및 host ID가 필요하고 client secret/partner API key는 요구하지 않는 흐름이다.[11] |
| identity vs inference | 웹사이트 identity-only의 `openid profile email`은 모델 접근권이 아니다. plan usage에는 `offline_access resource.invoke chatgpt.tokens.use.direct`와 반환 scope 확인이 별도로 필요하다.[13][11] |
| 추론 인터페이스 | 승인된 SIWC plan token은 `GET /v1/models`, `POST /v1/responses`의 bearer로 사용한다. HTTP는 `store:false`, `stream:true`, account-specific model 및 `response.completed` 확인이 필요하다. ChatGPT backend-api를 사용하지 않는다.[4] |
| 사용자 요금제 | quickstart는 적격 Plus/Pro 사용자의 본인 plan 사용을 설명한다. 운영자 구독 하나의 불특정 사용자 relay 허가가 아니다.[14][3] |
| credential 관리 | 발급 client/검증 identity별 분리, state/nonce/ID token 검증, 원자적 비밀 저장, 갱신 직렬화와 회전 refresh token 교체, 로그아웃 시 revocation 및 로컬 제거가 필요하다.[11][12] |
| 수명 | access token 1시간, refresh token 30일 및 성공 갱신 시 교체가 문서화되어 있다. 이는 SIWC 계약이며 Codex managed token의 동일 수명이라고 추정하지 않는다.[8] |
| remote VM | 같은 사용자/workspace의 OSS VM 절차는 있으나 이를 공개 다중 사용자 서비스의 승인으로 확대하지 않는다. 이번 작업은 어떤 credential 전송도 하지 않았다.[10][3] |
| app-server 경유 | SIWC token을 별도 Responses provider에 넣는 예시는 있지만 별도 Codex sign-in이 불필요한 다른 경로다. 현재 요구의 Codex login OAuth와 구별한다.[9] |
| 제약 | 일부 Responses 필드와 hosted 도구 미지원, 직접 HTTP history 전달, app-server의 로컬 shell/MCP/child-agent 가능성이 명시된다. unsupported hosted tools가 곧 zero-tools는 아니다.[5] |

따라서 **‘API 키 없는 공식 OAuth 추론은 존재하지 않는다’는 주장은 틀리지만, 현재 확정 요구/공개 Discord 구성에 즉시 사용 가능한 허가된 운영 경로를 확립한 것은 아니다.** SIWC 등록/동의/모델 호출은 수행하지 않았다.[11][4][15]

## 5. 사용자가 실제로 할 수 있는 다음 조치

**개발:** 확정된 Codex login OAuth transport의 구현·오프라인 검증을 계속한다. 이 문서는 재선택 요청이나 구현 중지 요청이 아니다.

**공개 운영 조건 문의:** app-server의 공식 안내가 제공하는 연락 진입점은 [OpenAI Sign in with ChatGPT interest form](https://openai.com/form/sign-in-with-chatgpt-interest/)이다. 이 URL은 공식 문서 링크에서 확인했으며 form 자체의 현재 제출 가능 상태는 검증하지 못했다. 이 양식은 SIWC 파트너 waitlist이지 **Codex OAuth 공개 relay의 승인 신청서라고 보증할 수 없다**. 기존 OpenAI 담당자가 있다면 아래 범위를 명시해 문의할 수 있다. 이번 작업은 제출하지 않는다.[15][2]

문의할 질문:

1. `codex login` managed OAuth를 사용하는 무료 OSS 공개 Discord bot은 hosted-service 제한 대상인가? app-server와 CLI 각각의 적용 범위는 무엇인가?
2. 운영자 구독의 공동 채널 답변과 사용자별 구독 연결은 각각 허용되는가? private self-hosted와 중앙 public hosting의 구분 기준은?
3. Codex login OAuth를 **유지한 채** 가능한 승인/계약이 있는가? 있다면 공식 등록 절차·계정 자격·지역/요금제·callback·갱신/철회·사용량 책임 계약은?
4. 공식 지원되는 text-only/zero-tools 설정 및 도구 집합 검증 방법은? read-only 이외의 사전 실행 금지 보증은?
5. 공개 채널 데이터 전송 동의, retention, history/rollout 삭제, 다른 사용자의 요청 대행에 추가 조건이 있는가?

허가가 불명확하면 **공개 서비스 활성화를 보류**하되, 로그인/배포 없는 구현과 검증을 계속할 수 있다. SIWC/API 키/다른 모델로 묵시 전환하지 않는다.

## 6. 검증·증거 범위

- 공식 OpenAI 문서의 실제 HTTPS Markdown 응답을 로컬 증거로 저장하고 URL ledger를 생성했다. 부모가 web.run을 실행했다는 잘못 전달된 문구는 근거로 사용하지 않았다.
- 인용문은 fetched text와 기계적으로 대조하고 이 문서의 citation ID/URL/evidence 연결을 검증한다. 이는 계약 법률 자문이나 실제 계정 접근 성공의 증거가 아니다.
- 최초 테스트는 `.runtime` 부모 디렉터리 누락으로 setup 오류가 났고 생성 후 재실행했다. 로컬 Python 3.9: **223 passed, 1 skipped**, compileall 성공. skip은 로컬 환경의 Linux 전용 조건이며 CI가 따로 검증한다.
- 문서 외 production 변경 없음. 최종 remote head와 CI는 PR readback으로 확인하고, 병합·배포하지 않는다.

## Sources

[2] https://developers.openai.com/siwc/request-client-id
    > "Sign in with ChatGPT is currently offered to a select group of commercial partners."
[3] https://developers.openai.com/siwc/token-sharing-open-source
    > "These docs explain ChatGPT plan usage for open-source and locally hosted apps."
[4] https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
    > "Set `store` to `false` and `stream` to `true` on each HTTP inference request in this flow."
[5] https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations
    > "Local tools and agents"
[8] https://developers.openai.com/siwc/token-sharing-open-source/token-reference
    > "Access tokens are valid for one hour"
[9] https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server
    > "No separate Codex sign-in is required."
[10] https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms
    > "Complete OAuth locally with the same tool/client for the same user and workspace you will use on the VM."
[11] https://developers.openai.com/siwc/token-sharing-open-source/sign-in
    > "This direct flow needs neither a client secret nor a partner API key."
[12] https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
    > "Store and use the latest replacement, and serialize refreshes for the same session so two processes do not race a rotating token."
[13] https://developers.openai.com/siwc/website
    > "This guide covers
identity scopes"
[14] https://developers.openai.com/siwc/quickstart
    > "ChatGPT plan usage is available to all open-source
partners and selected private clients."
[15] https://learn.chatgpt.com/docs/app-server
    > "App-server authentication has never been permitted for commercial or hosted services."
[18] https://developers.openai.com/codex/auth
    > "Run `codex login`, then complete the browser flow."
[20] https://developers.openai.com/codex/config-reference
    > "Enable command execution tools (stable; on by default)."
[21] https://learn.chatgpt.com/docs/agent-approvals-security
    > "commands allowed by the sandbox can run without approval"
