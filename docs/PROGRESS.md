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
