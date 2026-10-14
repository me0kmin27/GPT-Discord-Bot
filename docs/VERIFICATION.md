# 검증 범위 및 인계

## 로컬 실행 증거

- `python -m pytest -q --basetemp=.runtime/pytest`: **50 passed, 1 skipped** (macOS Python 3.9.6).
- skip은 `systemd-analyze` 부재에 따른 실제 unit 파서 검사 1건입니다. Ubuntu CI에서는 실행 대상입니다.
- `python -m compileall -q helperbot`, `git diff --check`: 성공.
- `pip install -e '.[test]'`: 실제 패키지/console entry point 설치 성공. 초기 pip 21의 editable 지원 오류는 가상환경 안에서 pip 업그레이드 후 해결했습니다.
- `discord-helper doctor`: disabled-codex, credentials_present=False 확인.
- `discord-helper ... run --check`: `Offline check OK: 6 commands; provider=disabled-codex; no network/login` 확인.

## 테스트 경계

- SQLite는 실제 임시 파일로 테스트합니다. 서버/채널/사용자/스레드 격리, 후보→확정, 권한 거절, 문맥 상한/초기화, 개인정보/메시지/채널/서버 삭제, 삭제 중 지연 응답 무효화를 검증합니다.
- Discord command tree와 실제 콜백을 구성하고 HTTP 경계만 대역으로 대체합니다. 봇 로그인·실서버 권한·출처 링크 접근은 미검증입니다.
- systemd 설치 파일 생성/재설치/덮어쓰기 거절/경로 인용, 서비스 명령과 상태 재조회, 설정 권한/심볼릭 링크 방어, 공식 Codex 로그인 명령의 전용 인증 경로를 검증합니다.
- systemctl 및 Codex/npm 자식 호출은 테스트 대역이며 실제 서비스나 실제 로그인으로 부르지 않습니다. 생성 unit의 Linux 파서 검사는 별도 테스트입니다.
- 운영 토큰/개인 Codex/Hermes 인증 파일을 읽지 않았습니다. 테스트 토큰 문자열은 합성 fixture입니다. 배포, 공개 모델 호출, 실제 Codex 로그인은 실행하지 않았습니다.

## 독립 검토 체크포인트

1. 최종 PR head의 CI와 테스트 재실행.
2. Discord 권한 경계/공개 스레드 정규화, 모든 SQL tenant 필터, 삭제 전파.
3. provider는 반드시 disabled이며 테스트 공급자를 실연동으로 광고하지 않는지 확인.
4. CLI의 credential 경로/권한/재설치 보존, systemd unit quoting/단일 프로세스 제한 확인.
5. 공개 저장소에 런타임 DB/인증/개인정보가 없고 개발 경로/토큰이 unit에 하드코딩되지 않았는지 확인.

GitHub 기능 브랜치의 백업은 승인되었지만, 작성자 자체 승인을 독립 검토로 취급하지 않습니다. 병합은 상위 작업자가 최종 head를 독립 검토한 뒤 처리합니다. 최종 원격 SHA와 CI 결과는 PR/인계 보고에서 확인합니다.
