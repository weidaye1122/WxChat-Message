#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/common.sh"
require_root
require_system
lock_installation
owned_installation || die '未找到由本脚本安装的 WxChat-Message。'
backup_dir="$(python3 "$SCRIPT_DIR/installer.py" backup)"
systemctl disable --now "$SERVICE"
rm -f "$UNIT_FILE"
systemctl daemon-reload
rm -rf -- "$APP_DIR"
echo 'WxChat-Message 已卸载，账号、配置和日志仍保留。'
echo "数据：$DATA_DIR"
echo "环境文件：$ENV_FILE"
echo "备份：$backup_dir"
echo '系统 Python、Nginx 及其他服务保留。'
