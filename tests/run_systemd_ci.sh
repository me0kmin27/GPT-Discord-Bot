#!/usr/bin/env bash
# GitHub-hosted disposable runner only. Never run against an operator account.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]]
[[ $(uname -s) == Linux && $(id -u) != 0 ]]
user="dhci${GITHUB_RUN_ID:?}${GITHUB_RUN_ATTEMPT:?}"
[[ "$user" =~ ^dhci[0-9]+$ && ${#user} -le 32 ]]
mode=${1:-normal}
[[ "$mode" == normal || "$mode" == --cleanup || "$mode" == --inject-failure ]]
python=$(command -v python)
owner() {
  sudo --preserve-env=GITHUB_ACTIONS,RUNNER_ENVIRONMENT,GITHUB_RUN_ID,GITHUB_RUN_ATTEMPT \
    "$python" tests/systemd_ci_owner.py "$1"
}
if [[ "$mode" == --cleanup ]]; then
  owner cleanup
  exit 0
fi
# Refuse preexisting state before arming recovery; do not adopt another run.
[[ ! -e "/run/$user.owned" && ! -L "/run/$user.owned" ]]
cleanup() {
  result=$?
  trap - EXIT INT TERM
  set +e
  action=cleanup
  if [[ "$mode" == --inject-failure && "$result" == 73 ]]; then
    action=inject-orphan
  fi
  owner "$action"
  cleanup_result=$?
  [[ "$action" != inject-orphan ]] || owner verify-orphan || cleanup_result=1
  if [[ "$result" == 0 && "$cleanup_result" != 0 ]]; then result=$cleanup_result; fi
  if [[ "$mode" == --inject-failure && "$cleanup_result" == 0 && "$result" == 73 ]]; then
    printf 'orphan_verified=true\n' >> "${GITHUB_OUTPUT:?}"
  fi
  printf 'Harness exit status: %s (cleanup status: %s)\n' "$result" "$cleanup_result"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
uid=$(owner prepare)
# Do not relax runner workspace permissions for the disposable account.
sudo install -o "$user" -g "$user" -m 600 tests/systemd_lifecycle.py tests/systemd_fixture.py "/home/$user/"
# Explicit test-only manager; no reliance on runner login/DBus, no lingering.
sudo systemctl start "user@${uid}.service"
owner runtime
sudo systemctl is-active "user@${uid}.service"
sudo -u "$user" env -i \
  HOME="/home/$user" USER="$user" LOGNAME="$user" \
  PATH="$(dirname "$python"):/usr/bin:/bin" \
  XDG_RUNTIME_DIR="/run/user/$uid" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" \
  "$python" "/home/$user/systemd_lifecycle.py" "$mode"
