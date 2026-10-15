# 기존 설치 업그레이드·백업·롤백

**`git pull`, GitHub 병합, 새 `install.sh` 재실행만으로 운영 Python 패키지는 바뀌지 않습니다.**
이 문서는 같은 Linux 사용자·같은 경로에서 수행하는 **수동 유지보수 절차**입니다.
자동 업그레이드/마이그레이션/롤백 명령은 제공하지 않습니다. 운영 서버에 적용할 권한,
중단 시간, 검토한 정확한 commit과 복구 가능성을 먼저 확보하세요.
신규 설치는 [INSTALL_KO.md](INSTALL_KO.md), 선택 GUI는 [WEB_GUI_KO.md](WEB_GUI_KO.md)입니다.

## 1. 실제 실행본과 변경 범위 확인

설치기 기본 경로 예시입니다. 아래 명령은 **Bash**에서 사용합니다.
XDG/custom 설치는 launcher와 두 unit의 Python/config/data/unit 경로를 로컬에서 확인하고
변수를 실제 경로로 바꾸세요. `sudo`나 다른 사용자로 실행하지 않습니다.

```bash
ROOT="$HOME/.local/share/discord-helper-install"
PY="$ROOT/venv/bin/python"
CLI="$ROOT/discord-helper"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/discord-helper"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/discord-helper"
UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

"$PY" -I -c 'import sys, helperbot; print(sys.executable); print(helperbot.__file__)'
"$PY" -I -m pip check
"$CLI" overview
systemctl --user show discord-helper.service discord-helper-web.service \
  -p LoadState -p ActiveState -p SubState -p UnitFileState -p MainPID -p NRestarts
```

- 오래된 버전에 `overview`가 없으면 위 `systemctl --user show`로 각각 확인합니다.
  `not-found`인 GUI는 설치되지 않은 것이지 고장이 아닙니다.
- `app`의 HEAD, `installer.json`은 **bootstrap 고정 revision**입니다. 실제 import가
  `venv/.../site-packages/helperbot`이면 `app` 소스만 변경해도 실행본은 그대로입니다.
  패키지 버전 `0.1.0`만으로 commit을 식별할 수도 없습니다.
- unit/drop-in은 로컬에서 검토하되 환경/로그에 비밀이 있을 수 있으므로 원문을 공개하지 마세요.
  각 서비스가 실행 중이었는지, enabled/disabled/masked인지와 linger 정책을 기록합니다.
- 새 commit의 Python 요구사항, `pyproject.toml`, Codex pin, DB 스키마 및 설정 변경을 검토합니다.
  Codex/tools 또는 Python 경로 변경이 필요한 경우 이 패키지 교체 예시만으로는 충분하지 않습니다.
  별도 검증된 마이그레이션이 없으면 중단하세요. 파일 몇 개만 복사하는 혼합 버전은 피합니다.

## 2. 서비스를 멈추고 private 백업

GUI 설정 저장과 봇 DB 쓰기가 모두 멈춰야 일관된 백업이 됩니다. 설치되어 있는 두 unit을
각각 중지하고 `ActiveState=inactive`, `MainPID=0`을 확인하세요. 전경 실행 프로세스도
Ctrl+C로 종료합니다. 실패/중지 불명/다른 writer가 있으면 백업·교체를 진행하지 마세요.
`stop`은 enable/disable 또는 linger 정책을 변경하지 않습니다.

```bash
# 존재하는 unit에 대해서만 실행 (GUI 미설치라면 두 번째 명령 생략)
systemctl --user stop discord-helper.service
systemctl --user stop discord-helper-web.service
systemctl --user show discord-helper.service discord-helper-web.service \
  -p LoadState -p ActiveState -p SubState -p MainPID
```

다음은 **기본 설치에 대한 백업 예시**입니다. 경로 존재/소유권/여유 공간을 확인한 뒤 실행하고,
어느 명령이든 실패하면 다음 단계로 넘어가지 마세요. 백업은 Git checkout 밖에 둡니다.

```bash
umask 077
BACKUP=$(mktemp -d "$HOME/discord-helper-backup.XXXXXXXX")
cp -a "$ROOT" "$BACKUP/install"
cp -a "$CONFIG" "$BACKUP/config"
cp -a "$DATA" "$BACKUP/data"
mkdir "$BACKUP/units"
for unit in discord-helper.service discord-helper-web.service; do
  for entry in "$UNITS/$unit" "$UNITS/$unit.d"; do
    if [ -e "$entry" ]; then cp -a "$entry" "$BACKUP/units/"; fi
  done
done
"$PY" -I -m pip freeze > "$BACKUP/pip-freeze.txt"
```

전체 설치 root에는 venv·launcher·bootstrap marker/checkout이 포함됩니다. 전체 data에는
`state.db`와 SQLite 동반 파일, 앱 OAuth, tools가 포함됩니다. runtime.json의 **provider,
sync_guild, 중첩 codex 모델/effort/검색/단계별 예산**과 Discord 토큰, GUI 관리자도 보존합니다.
이 백업은 **인증정보와 사용자 데이터를 포함**합니다. mode 700/600 접근 통제와 승인된 암호화
보관·보존기한을 적용하고 공개 GitHub/이슈/공유 드라이브에 올리지 마세요. 다른 앱의 OAuth를
가져오지 않습니다. 백업 파일 존재·복사 완료와 복구 경로를 로컬에서 확인해야 합니다.

## 3. 검토한 소스를 전체 패키지로 설치

bootstrap의 `app`, `installer.json`, `software-ready`를 수정/삭제해서 검사를 우회하지 마세요.
별도 **깨끗한 checkout**을 검토한 전체 SHA에 고정합니다. 아래 대문자 값은 실제 검토 결과로
교체해야 하며 그대로 실행할 값이 아닙니다. 내려받기/검토는 서비스 중지 전에 준비해도 됩니다.

```bash
SOURCE='/absolute/path/to/reviewed/GPT-Discord-Bot'
REVIEWED_SHA='REPLACE_WITH_REVIEWED_40_CHARACTER_COMMIT_SHA'
[[ "$REVIEWED_SHA" =~ ^[0-9a-f]{40}$ ]] && \
  test "$(git -C "$SOURCE" rev-parse HEAD)" = "$REVIEWED_SHA" && \
  test -z "$(git -C "$SOURCE" status --porcelain)"
```

위 검사가 성공하고 diff/CI/독립 검토를 확인했을 때만 진행합니다. 브랜치명 `main`은
움직이므로 설치 근거로 충분하지 않습니다. 기존 GUI 사용 여부에 맞춰 **둘 중 하나만** 실행:

```bash
# CLI만 사용
"$PY" -I -m pip install "$SOURCE"
# 또는 GUI 사용/명시적으로 추가 (기존 GUI 설치는 반드시 [web]도 검증)
"$PY" -I -m pip install "${SOURCE}[web]"
```

기본 **build isolation을 유지**하세요. lean runtime venv에 setuptools/build 도구가 없을 수
있으므로 `--no-build-isolation`을 복구 요령으로 쓰지 않습니다. `--no-deps`로 필요한 의존성
설치를 생략하지 않습니다. 실패 시 일부 파일/의존성만 교체됐을 수 있으므로 서비스를 시작하지
말고 아래 롤백으로 돌아갑니다. pip 설치는 원자적 배포가 아닙니다.

```bash
"$PY" -I -m pip check
"$PY" -I -m helperbot.manage --help
"$PY" -I -c 'import helperbot; print(helperbot.__file__)'
"$CLI" settings show
```

설정 출력에는 실제 서버/모델 값이 있을 수 있으므로 로컬 비교만 합니다. 백업과 runtime.json의
바이트 비교, credentials/OAuth/GUI 관리자 보존 여부를 **내용을 출력하지 않고** 확인하세요.
설치된 helperbot 전체 파일(templates/static 포함)을 검토한 소스와 비교하고, 확인한 SHA·Python
경로·pip freeze를 private 운영 기록에 남깁니다. pip check만으로 소스 동일성이 증명되지는 않습니다.

현재 Codex 설치를 사용하는 인증 없는 offline check는 별도 임시 DB로 실행할 수 있습니다:

```bash
"$PY" -I - "$CONFIG" "$DATA" "$UNITS" <<'PY'
import sys
from pathlib import Path
from helperbot.bootstrap import offline_check
from helperbot.manage import Paths
offline_check(Paths(*(Path(value) for value in sys.argv[1:])))
PY
```

이 검사는 고정 Codex native binary 발견과 임시 스키마만 확인하며 **저장된 codex 옵션 전체,
OAuth 로그인, 실제 추론, Discord 연결을 검증하지 않습니다**. `settings show`로 설정 유효성도
별도로 확인합니다. 평소 `run --check`는 지정한 data의 실제 DB를 열 수 있으므로 이를 실행 중
운영 DB에 대한 무해한 읽기 명령으로 취급하지 마세요.

수동 패키지 교체 뒤 bootstrap marker/`app`은 최초 설치 snapshot으로 남습니다.
**이후 `bash install.sh`는 업그레이드/롤백 수단으로 사용하지 않습니다.** 정상 `software-ready`가
있으면 pip 재설치를 건너뛰며, marker와 checkout이 다르면 거절합니다. marker는 실행 중인
패키지의 provenance가 아닙니다. 재실행 보장 대신 이 수동 관리 절차와 별도 SHA 기록을 사용하세요.

## 4. 필요한 서비스만 재개·검증

- 이전에 실행 중이던 서비스만 각각 `systemctl --user start discord-helper.service` /
  `systemctl --user start discord-helper-web.service`로 재개합니다. 원래 중지한 서비스는
  그대로 둡니다. GUI 미설치 환경에서 새 서비스/관리자 생성은 [별도 선택](WEB_GUI_KO.md)입니다.
- `"$CLI" overview`와 `systemctl --user show …`로 새 PID, ActiveState/SubState,
  Result/ExecMainStatus/NRestarts를 잠시 후 다시 확인합니다. 재시작 반복은 실패입니다.
  기존 disabled 정책을 유지하고 enable/linger를 몰래 추가하지 않습니다.
- GUI가 있다면 서버 loopback의 `/login` HTTP 200, `/` 로그인 redirect를 확인하고
  **서버와 같은 포트**의 SSH 터널을 통해 실제 로그인합니다. 기본은 8765이며 LAN 공개는 하지 않습니다.
- 설정 **저장 ≠ 적용**, systemd active ≠ OAuth 추론 ≠ Discord 준비 완료입니다.
  승인된 테스트 guild/채널에서 `/channel enabled:true`, `/ask`, 후보 저장과 수동 `/resolved`
  흐름을 별도 확인합니다. 로그인 성공이나 오프라인 테스트만으로 실응답 성공을 보고하지 않습니다.

## 5. 실패 시 롤백 한계

1. 봇/GUI/전경 writer를 다시 모두 중지하고 정지 상태를 확인합니다.
2. 실패한 venv는 진단용 private 위치로 옮기고 백업 `install/venv`를 **원래 ROOT/venv 경로**에
   복원합니다. venv 실행 파일에는 절대 경로가 있어 백업 디렉터리에서 직접 실행하면 안 됩니다.
   동일 호스트/사용자/Python 기반의 단기 복구용이며 다른 OS/Python으로의 이식 백업은 아닙니다.
3. config는 코드와 함께 호환성을 검토해 복원합니다. 새 옵션을 구버전이 거절할 수 있습니다.
   DB 스키마가 바뀌었다면 구버전 코드만 되돌리지 마세요. 필요한 경우 정지 시점 data snapshot을
   일관되게 복원하되, **그 이후 사례/설정 변경·삭제가 사라지거나 삭제 자료가 되살아날 수 있음**을
   먼저 판단합니다. OAuth는 만료/회전/해지로 재로그인이 필요할 수 있습니다.
4. 변경한 unit/drop-in/launcher가 있다면 백업과 비교하여 해당 항목만 원래 경로에 복원하고
   `systemctl --user daemon-reload`합니다. 공유 user-unit 디렉터리를 통째로 덮어쓰지 않습니다.
5. pip check·import 경로·설정·정책을 다시 확인하고 원래 실행하던 서비스만 시작하여 위 검증을
   반복합니다. 복구 검증이 안 되면 중지 상태를 유지합니다.

`pip freeze`는 artifact 보관이나 완전한 재현 lock이 아닙니다. 저장소 SHA도 외부 의존성의
미래 가용성을 보장하지 않습니다. venv/config/data 백업은 외부 Discord 게시물, 원격 계정 상태,
백업 이후 삭제 요청까지 되돌리지 않습니다. 자동 DB downgrade/백업 삭제 기능은 없습니다.
