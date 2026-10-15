#!/usr/bin/env bash

APP_DIR=/opt/wxchat-message
DATA_DIR=/var/lib/wxchat-message
ENV_FILE=/etc/wxchat-message.env
UNIT_FILE=/etc/systemd/system/wxchat-message.service
BACKUP_ROOT=/var/backups/wxchat-message
SERVICE=wxchat-message.service
SERVICE_USER=wxchat-message

die() { echo "错误：$*" >&2; exit 1; }
require_root() { [[ $EUID -eq 0 ]] || die '请使用 root 运行。'; }
require_system() {
  [[ "$(uname -s)" == Linux && -f /etc/os-release ]] || die '一键安装需要 Debian / Ubuntu Linux 系统。'
  # /etc/os-release is maintained by the operating system.
  . /etc/os-release
  [[ "$ID" == debian || "$ID" == ubuntu ]] || die '当前支持 Debian / Ubuntu。'
  command -v apt-get >/dev/null || die '未找到 apt-get。'
  command -v systemctl >/dev/null && [[ -d /run/systemd/system ]] || die '需要正在运行的 systemd。'
  command -v flock >/dev/null || die '需要 util-linux 提供的 flock。'
}
lock_installation() {
  exec 9>/run/wxchat-message-install.lock
  flock -n 9 || die '已有安装、升级或卸载任务正在运行。'
}
owned_installation() { [[ -f "$APP_DIR/.wxchat-message-install" ]] && grep -qx 'WxChat-Message' "$APP_DIR/.wxchat-message-install"; }
