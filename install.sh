#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" == --help ]]; then
  echo '安装或升级 WxChat-Message（Debian 12+ / Ubuntu 22.04+，systemd）。'
  echo '默认安装最新正式 Release；WXCHAT_VERSION 可显式指定标签、分支或提交。'
  echo '在本地源码目录运行时，安装当前检出的源码。'
  echo '可选变量：WXCHAT_VERSION、WXCHAT_ADMIN_HOST、WXCHAT_ADMIN_PORT、WXCHAT_SETUP_ALLOWED_IPS、WXCHAT_PROXY_PORT、WXCHAT_PROXY_HOST。'
  exit 0
fi
[[ $# -eq 0 ]] || { echo '不支持的参数，请使用 --help。' >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo '请使用 root 运行安装脚本。' >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
if [[ -f "${SCRIPT_DIR:-}/scripts/install.sh" && -f "${SCRIPT_DIR:-}/app.py" ]]; then
  echo '从本地源码安装，请确认当前检出的版本。'
  exec bash "$SCRIPT_DIR/scripts/install.sh"
fi

REF="${WXCHAT_VERSION:-}"
REPO="${WXCHAT_REPO_URL:-https://github.com/weidaye1122/WxChat-Message}"
REPO="${REPO%/}"
if command -v wget >/dev/null 2>&1; then
  download() { wget --timeout=30 --tries=3 --server-response -qO "$2" "$1" 2> "$work/response.headers"; }
elif command -v curl >/dev/null 2>&1; then
  download() { curl --connect-timeout 15 --max-time 120 --retry 2 -fsSL -D "$work/response.headers" "$1" -o "$2"; }
else
  echo '需要先安装 wget 或 curl。' >&2
  exit 1
fi

work="$(mktemp -d -t wxchat-message-download.XXXXXX)"
trap 'rm -rf -- "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

archive_ref="$REF"
if [[ -z "$REF" ]]; then
  echo '查找最新正式 Release ...'
  # GitHub 的 latest 入口只指向正式发布；通过重定向取标签，无需预装 Python 或 jq。
  if ! download "$REPO/releases/latest" /dev/null; then
    echo '无法获取正式 Release：可能尚未发布或网络不可达。未安装或升级，不会回退到 main。' >&2
    exit 1
  fi
  location="$(awk 'tolower($1) == "location:" { $1=""; sub(/^[[:space:]]+/, ""); sub(/\r$/, ""); sub(/ \[following\]$/, ""); target=$0 } END { print target }' "$work/response.headers")"
  case "$location" in
    http://*|https://*) ;;
    /*) authority="${REPO#*://}"; location="${REPO%%://*}://${authority%%/*}$location" ;;
    *) location="$REPO/releases/$location" ;;
  esac
  [[ "$location" == "$REPO/releases/tag/"* ]] || {
    echo '正式 Release 地址无效，已停止安装，不会回退到 main。' >&2; exit 1;
  }
  REF="${location#"$REPO/releases/tag/"}"
  archive_ref="refs/tags/$REF"
fi
[[ "$REF" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ && "$REF" != *..* ]] || { echo '版本或分支名称无效。' >&2; exit 1; }
echo "下载 WxChat-Message $REF ..."
if ! download "$REPO/archive/$archive_ref.tar.gz" "$work/source.tar.gz"; then
  echo "无法下载版本 $REF，未安装或升级。" >&2
  exit 1
fi
mkdir "$work/source"
tar -xzf "$work/source.tar.gz" --no-same-owner --strip-components=1 -C "$work/source"
[[ -f "$work/source/scripts/install.sh" && -f "$work/source/scripts/common.sh" && -f "$work/source/app.py" ]] || {
  echo '安装包内容不完整。' >&2; exit 1;
}
export WXCHAT_VERSION="$REF"
bash "$work/source/scripts/install.sh"
