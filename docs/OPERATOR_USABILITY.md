# CLI / GUI 운영 편의성 — 한정된 개선 범위

## 완료 기준과 경계

이 범위의 **100% = 설계 조사 + CLI/GUI 구현 + 테스트 + 독립 리뷰 + 최종 SHA CI + main 병합**입니다.
이번 작업은 **PR 생성까지이며 병합 금지**입니다. 따라서 병합 전에는 100%로 보고하지 않습니다.
배포는 이 기준과 별도입니다. 운영 서버 서비스 시작/중지, enable, Linger, 설치 교체, 포트 공개는 하지 않습니다.

- [x] fresh main `9112ff02cd8f27de282b2bb28e1ded145efc3782`와 열린 PR 조사 (시작 시 0개).
- [x] manage / settings_ops / web_service / web_admin / 템플릿 / pytest / installed-browser CI 조사.
- [x] 공유된 읽기 전용 상태 조회: bot/web 분리, 상태/자동 시작 구분, 고정 명령 안내.
- [x] CLI `overview` / `overview --json`, 잘못된 manage.py 직접 실행 안내.
- [x] GUI 상태 카드, 저장 설정 vs 실제 적용 미확인 표시 유지, 실제 포트 접속 안내.
- [x] 전체 테스트, 설치 wheel CLI / 실제 Chromium 흐름의 증거 (581 passed, 1 skipped; 7 screenshots).
- [ ] 독립 리뷰 및 최종 SHA CI.
- [ ] main 병합 (이번 요청에서 수행 금지).
- [ ] 운영 배포 (별도 승인 필요).

## 발견 사항 / 설계

기존 `status`는 봇만 대상으로 하며 CLI의 raw systemctl 출력과 종료 코드를 유지합니다.
GUI의 기존 settings_ops.service_status는 봇의 안전한 필드만 읽습니다.
새 `overview`는 이 조회를 고정된 두 유닛으로 확장하며 기존 명령의 의미를 바꾸지 않습니다.
LoadState / UnitFileState를 추가로 보여주고 `inactive + loaded`일 때만 시작 명령을 안내합니다.
미설치, masked, 조회 실패를 단순 중지로 오인하지 않습니다. Linger는 조회하지 않으며 미확인이라고 명시합니다.
서비스 상태는 스냅샷입니다. active, saved revision, GUI 접속 성공 중 어느 것도 봇의 실제 설정 적용이나 Discord/OAuth 성공을 증명하지 않습니다.
설정 검증/원자적 저장/선택 설정의 존재 여부 모델은 기존 공유 구현 그대로입니다.

## 운영자가 먼저 할 일 (명령 안내일 뿐 자동 실행 없음)

설치된 환경의 CLI로 실행하세요. `sudo python3 manage.py start`는 올바른 진입점이 아닙니다.
설치 루트의 소스와 실제 site-packages가 다를 수 있으므로 설치된 interpreter를 확인합니다.
기본 설치 경로를 사용했다면:

```sh
~/.local/share/discord-helper-install/venv/bin/discord-helper overview
~/.local/share/discord-helper-install/venv/bin/python -m helperbot.manage overview --json
~/.local/share/discord-helper-install/venv/bin/python -c 'import helperbot.manage; print(helperbot.manage.__file__)'
```

`overview`는 두 고정 사용자 유닛의 상태만 읽습니다. 설정/토큰/OAuth/DB를 읽거나 쓰지 않습니다.
사용자 지정 config/data/unit 옵션은 설정 및 설치 작업에 맞게 지정해야 하며, 상태 조회는 언제나 현재 사용자 systemd의 고정 유닛을 대상으로 합니다.
상태 조회 불가는 종료 코드 0의 JSON에서도 `available: false`로 표현됩니다. 이는 건강함을 뜻하지 않습니다.

- 봇만 시작: `discord-helper start`
- GUI만 시작: `discord-helper gui start`
- 미설치: 설치된 경로와 기존 유닛을 검토한 뒤 `discord-helper install` / `discord-helper gui install`
- GUI 관리자 미설정: 서비스 계정의 로컬 대화형 터미널에서 `discord-helper gui setup`
- systemd 없는 개발 환경: `discord-helper run` / `discord-helper gui run` (각각 별도 전경 프로세스)
- 저장된 설정: `discord-helper settings show`; 저장만으로 재시작하지 않습니다.
- 서비스 시작은 enable 또는 Linger 변경을 승인하지 않습니다. disabled는 자동 시작 정책이고 inactive는 현재 실행 상태입니다.

## 원격 GUI 접속

기본 포트가 8765인 경우 로컬 PC에서 (USER@HOST는 서버 계정으로 교체):

```sh
ssh -N -L 8765:127.0.0.1:8765 USER@HOST
```

그다음 브라우저에서 `http://127.0.0.1:8765`를 엽니다.
사용자 지정 포트는 로컬/원격 양쪽 포트를 동일하게 맞추세요. GUI 안내는 실행 중인 GUI 포트로 표시됩니다.
Host/Origin 제한 때문에 LAN URL이나 bind-only 변경은 해결책이 아닙니다.
GUI에서 제공하는 명령은 텍스트이며 버튼으로 실행하지 않습니다. 기존 재시작 확인/CSRF 경계는 그대로입니다.

## 검증 재현

```sh
python -m pip install '.[test,web]' build playwright==1.60.0
mkdir -p .runtime
python -m pytest -q --basetemp=.runtime/pytest
python -m build --wheel
# 별도 가상환경에 생성 wheel과 playwright 설치 후 소스 밖 디렉터리에서:
python /path/to/checkout/tests/web_browser_smoke.py /path/to/synthetic-evidence
```

브라우저 검증은 임시 합성 관리자/토큰/OAuth/DB만 사용합니다. 실제 서비스 재시작은 누르지 않으며,
확인 화면 취소, 로그인/로그아웃, 저장 및 CLI readback, 오류/CSRF, 모바일 폭을 검증합니다.
운영 서비스/실제 OAuth 추론/Discord 전송/실제 설정 적용은 증거 범위 밖입니다.

## 구현 검증 기록

- RED: overview 함수 미구현/유닛 선택 인자 미지원으로 3개 실패 → 공유 구현 후 6개 통과.
- RED: CLI overview 인자 거부 + GUI에 web 유닛 안내 없음으로 2개 실패 → CLI/GUI 구현 후 관련 47개 통과.
- RED: manage.py 직접 실행이 traceback/exit 1을 출력 → 명시적 안내/exit 2 구현.
- 전체 기본 pytest: **581 passed, 1 skipped**, Python 3.9/macOS. skip은 Linux 전용 조건이며 Linux CI로 별도 확인합니다.
- non-editable wheel 설치 후 소스 밖 작업 디렉터리에서 실제 Waitress + Chromium:
  로그인, 설정 저장/CLI readback, 선택값 존재 보존, 검증 오류, CSRF 차단,
  재시작 확인 취소, 두 서비스 카드, 실제 포트 SSH 안내, 390px 화면 통과.
- 로컬 증거: `.runtime/pytest.log`, `.runtime/browser-evidence/manifest.json`,
  `.runtime/browser-evidence/config-readback.json`, 7개 PNG.
- 독립 리뷰는 PR의 정확한 최종 head에서 별도 수행해야 합니다. 구현자의 자체 검토를 독립 리뷰로 계산하지 않습니다.
- CI / 독립 리뷰 / 병합 상태는 PR의 최신 head를 확인하세요. 이 문서는 green CI나 병합 완료를 주장하지 않습니다.
