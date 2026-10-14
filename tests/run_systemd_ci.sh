#!/usr/bin/env bash
# GitHub-hosted disposable runner only. Never run against an operator account.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]]
[[ $(uname -s) == Linux && $(id -u) != 0 ]]
user="dhci${GITHUB_RUN_ID:?}${GITHUB_RUN_ATTEMPT:?}"
[[ "$user" =~ ^dhci[0-9]+$ && ${#user} -le 32 ]]
if [[ ${1:-} != --cleanup ]] && id "$user" >/dev/null 2>&1; then
  printf 'Refusing existing account: %s\n' "$user" >&2
  exit 1
fi
python=$(command -v python)
uid=''
created=false
cleanup() {
  result=$?
  trap - EXIT
  set +e
  if [[ "$created" == true ]]; then
    if [[ -n "$uid" ]]; then
      sudo systemctl stop "user@${uid}.service"
      sudo loginctl terminate-user "$user"
      sudo systemctl stop "user-runtime-dir@${uid}.service"
    fi
    sudo userdel --remove "$user"
    if id "$user" >/dev/null 2>&1 || [[ -e "/home/$user" ]] || { [[ -n "$uid" ]] && [[ -e "/run/user/$uid" ]]; }; then
      printf 'FAIL: disposable account/home/runtime cleanup incomplete\n' >&2
      result=1
    else
      printf 'PASS: disposable manager/account/home/runtime removed (no linger enabled)\n'
    fi
  fi
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ ${1:-} == --cleanup ]]; then
  if [[ -f "${RUNNER_TEMP:?}/$user.created" ]] && id "$user" >/dev/null 2>&1; then
    created=true
    uid=$(id -u "$user")
  fi
  exit 0
fi
sudo useradd --create-home --shell /bin/bash "$user"
created=true
touch "${RUNNER_TEMP:?}/$user.created"
uid=$(id -u "$user")
# Explicit test-only manager; no reliance on runner login/DBus, no lingering.
sudo systemctl start "user@${uid}.service"
sudo systemctl is-active "user@${uid}.service"
sudo -u "$user" env -i \
  HOME="/home/$user" USER="$user" LOGNAME="$user" \
  PATH="$(dirname "$python"):/usr/bin:/bin" \
  XDG_RUNTIME_DIR="/run/user/$uid" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
  "$python" "$PWD/tests/systemd_lifecycle.py"
