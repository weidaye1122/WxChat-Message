#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" == --help ]]; then
  echo '安装或升级 WxChat-Message（Debian 12+ / Ubuntu 22.04+，systemd）。'
  echo '可选变量：WXCHAT_VERSION、WXCHAT_ADMIN_PORT、WXCHAT_PROXY_PORT、WXCHAT_PROXY_HOST。'
  exit 0
fi
[[ $# -eq 0 ]] || { echo '不支持的参数，请使用 --help。' >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo '请使用 root 运行安装脚本。' >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
if [[ -f "${SCRIPT_DIR:-}/scripts/install.sh" && -f "${SCRIPT_DIR:-}/app.py" ]]; then
  exec bash "$SCRIPT_DIR/scripts/install.sh"
fi

REF="${WXCHAT_VERSION:-main}"
[[ "$REF" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ && "$REF" != *..* ]] || { echo '版本或分支名称无效。' >&2; exit 1; }
REPO="${WXCHAT_REPO_URL:-https://github.com/weidaye1122/WxChat-Message}"
if command -v wget >/dev/null 2>&1; then
  download() { wget --timeout=30 --tries=3 -qO "$2" "$1"; }
elif command -v curl >/dev/null 2>&1; then
  download() { curl --connect-timeout 15 --max-time 120 --retry 2 -fsSL "$1" -o "$2"; }
else
  echo '需要先安装 wget 或 curl。' >&2
  exit 1
fi

work="$(mktemp -d -t wxchat-message-download.XXXXXX)"
trap 'rm -rf -- "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "下载 WxChat-Message $REF ..."
download "${REPO%/}/archive/$REF.tar.gz" "$work/source.tar.gz"
mkdir "$work/source"
tar -xzf "$work/source.tar.gz" --no-same-owner --strip-components=1 -C "$work/source"
[[ -f "$work/source/scripts/install.sh" && -f "$work/source/scripts/common.sh" && -f "$work/source/app.py" ]] || {
  echo '安装包内容不完整。' >&2; exit 1;
}
export WXCHAT_VERSION="$REF"
bash "$work/source/scripts/install.sh"
