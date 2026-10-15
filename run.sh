#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -x "$APP_ROOT/.venv/bin/python" ]]; then
  python3 -m venv "$APP_ROOT/.venv"
  "$APP_ROOT/.venv/bin/python" -m pip install -r "$APP_ROOT/requirements.txt"
fi
exec "$APP_ROOT/.venv/bin/python" "$APP_ROOT/app.py" "$@"
