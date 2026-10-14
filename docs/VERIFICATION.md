# 검증 범위 및 인계

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
- `tests/test_receipt_races.py`는 실제 command tree/callback, gateway callback, Service, disabled provider, SQLite를 사용하며 HTTP 호출만 대체합니다. `send_message`와 `original_response` 양쪽 대기, single/bulk 삭제, 본인 삭제 및 아직 연결되지 않은 moderator resolver 삭제, reset/forget/채널 비활성화/스레드·채널·서버 삭제, 재활성화, 다른 서버·채널·사용자 격리, service 대기 중 근거 삭제, HTTP 실패/태스크 취소 후 정리를 검증합니다.
- receipt를 보내는 **첫 await 전** 활성 작업을 등록하고, await에서 돌아온 직후 취소를 검사한 다음 삽입/확정합니다. receipt ID를 아직 모를 때는 같은 guild/conversation의 어떤 메시지 삭제라도 해당 대기 작업을 보수적으로 취소합니다. ID를 확인한 뒤에는 이 보수적 모드를 종료합니다. 다른 guild/conversation의 무관한 삭제는 취소하지 않습니다.
- `/privacy_delete`는 기존 행이 없어도 해당 서버/사용자의 진행 중 작업을 무효화합니다. 삭제되는 사례가 다른 요청의 근거일 수 있으므로 실제 영향을 받는 parent-channel tenant의 요청도 무효화합니다. 전역 revision 대신 작업별 취소 플래그를 사용하여 다른 tenant의 삭제가 응답을 막지 않습니다.
- 영구 message-ID tombstone이나 사용자별 revision 사전은 없습니다. 메타데이터는 활성 작업 수에만 비례하며 성공/거절/예외/태스크 취소 시 `finally`에서 제거됩니다. 이미 취소된 작업은 재활성화로 복구되지 않고 새 명령은 정상 처리할 수 있습니다.

### 남아 있는 경계

- 단일 프로세스/이벤트 루프의 Store 및 전달된 gateway 이벤트에 대한 보장입니다. 오프라인 중 놓친 삭제 이벤트의 재조정이나 여러 프로세스 사이의 취소 전파는 구현하지 않았습니다.
- receipt ID를 모르는 짧은 구간에서 같은 conversation의 **무관한 메시지 삭제도 재시도를 요구할 수 있습니다**. 이는 무제한 tombstone 보관 대신 선택한 fail-closed 동작입니다.
- 삭제는 로컬 저장소와 아직 제출하지 않은 응답을 보호합니다. 이미 Discord에 제출된 receipt/embed, 진행 중인 HTTP 전송, 외부 백업을 원격으로 되돌리는 보장은 아닙니다. 사용자 안내대로 Discord 게시물/외부 백업 삭제는 별도입니다.
- live provider는 계속 disabled입니다. 실 Discord/모델 로그인, 배포, 운영 인증 파일 읽기는 하지 않았습니다. 최종 head의 원격 SHA/CI는 push 후 별도로 읽어 검증하며, 독립 검토 전 병합하지 않습니다.

## 독립 검토 체크포인트

1. 최종 PR head의 CI와 테스트 재실행.
2. Discord 권한 경계/공개 스레드 정규화, 모든 SQL tenant 필터, 삭제 전파.
3. provider는 반드시 disabled이며 테스트 공급자를 실연동으로 광고하지 않는지 확인.
4. CLI의 credential 경로/권한/재설치 보존, systemd unit quoting/단일 프로세스 제한 확인.
5. 공개 저장소에 런타임 DB/인증/개인정보가 없고 개발 경로/토큰이 unit에 하드코딩되지 않았는지 확인.

GitHub 기능 브랜치의 백업은 승인되었지만, 작성자 자체 승인을 독립 검토로 취급하지 않습니다. 병합은 상위 작업자가 최종 head를 독립 검토한 뒤 처리합니다. 최종 원격 SHA와 CI 결과는 PR/인계 보고에서 확인합니다.
