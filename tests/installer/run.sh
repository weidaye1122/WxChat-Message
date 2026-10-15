#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE=wxchat-message-installer-test:local
NAME="wxchat-message-install-qa-$$"
snapshot="$(mktemp -d -t wxchat-message-test-source.XXXXXX)"
cleanup() {
  local code=$?
  trap - EXIT
  if [[ $code -ne 0 ]]; then docker logs --tail 60 "$NAME" 2>/dev/null || true; fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf -- "$snapshot"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 - "$ROOT" "$snapshot" <<'PY'
from pathlib import Path
import shutil,sys
source,destination=map(Path,sys.argv[1:])
for name in ['app.py','proxy.py','requirements.lock','requirements.txt','README.md','LICENSE','install.sh']:
    shutil.copy2(source/name,destination/name)
for name in ['static','scripts','deploy','tests']:
    shutil.copytree(source/name,destination/name,ignore=shutil.ignore_patterns('__pycache__','.DS_Store','*.pyc'))
PY
chmod 755 "$snapshot"
docker build -t "$IMAGE" -f "$ROOT/tests/installer/Dockerfile" "$ROOT/tests/installer"
docker run -d --name "$NAME" --privileged --cgroupns=private \
  --tmpfs /run --tmpfs /run/lock --tmpfs /tmp \
  --mount "type=bind,source=$snapshot,target=/src,readonly" "$IMAGE" >/dev/null
ready=0
for _ in {1..30}; do
  state="$(docker exec "$NAME" systemctl is-system-running 2>/dev/null || true)"
  if [[ "$state" == running || "$state" == degraded ]]; then ready=1; break; fi
  sleep 1
done
[[ $ready -eq 1 ]] || { echo '隔离容器中的 systemd 未能启动。' >&2; exit 1; }
docker exec "$NAME" python3 /src/tests/installer/check_install.py
