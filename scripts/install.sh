#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
. "$SCRIPT_DIR/common.sh"
require_root
require_system
lock_installation
for file in app.py proxy.py requirements.lock scripts/installer.py deploy/wxchat-message.service; do
  [[ -f "$SOURCE_DIR/$file" ]] || die "安装包缺少 $file。"
done
[[ ! -e "$APP_DIR" ]] || owned_installation || die "$APP_DIR 已存在且不属于本安装脚本。"
[[ ! -e "$UNIT_FILE" ]] || owned_installation || die "$UNIT_FILE 已存在，请先核对服务归属。"

work="$(mktemp -d -t wxchat-message-install.XXXXXX)"
release='' old_release='' switched=0 success=0 policy_saved=0 policy_active=0 new_nginx=0 policy_work=''
old_active=0 old_enabled=0 had_unit=0 had_env=0
[[ ! -f "$UNIT_FILE" ]] || { cp -a "$UNIT_FILE" "$work/previous.service"; had_unit=1; }
[[ ! -f "$ENV_FILE" ]] || had_env=1
if owned_installation; then
  if [[ -L "$APP_DIR/current" ]]; then old_release="$(readlink -f "$APP_DIR/current")"; fi
  [[ ! -e "$APP_DIR/current" || -L "$APP_DIR/current" ]] || die 'current 必须是由安装器管理的链接。'
  [[ -z "$old_release" || "$old_release" == "$APP_DIR/releases/"* ]] || die '现有 current 链接不属于本项目的 releases 目录。'
  if systemctl is-active --quiet "$SERVICE"; then old_active=1; fi
  if systemctl is-enabled --quiet "$SERVICE"; then old_enabled=1; fi
fi

restore_policy() {
  if [[ $policy_active -eq 1 ]]; then
    rm -f /usr/sbin/policy-rc.d
    [[ $policy_saved -eq 0 ]] || mv "$policy_work/policy.original" /usr/sbin/policy-rc.d
    policy_active=0
    rm -rf -- "$policy_work"
  fi
}
switch_release() {
  ln -s "$1" "$APP_DIR/.current-install-$$"
  mv -Tf "$APP_DIR/.current-install-$$" "$APP_DIR/current"
}
cleanup() {
  local code=$?
  trap - EXIT INT TERM
  set +e
  restore_policy
  [[ -z "$policy_work" ]] || rm -rf -- "$policy_work"
  if [[ $new_nginx -eq 1 ]]; then
    systemctl disable nginx.service >/dev/null 2>&1
  fi
  if [[ $success -eq 0 && $switched -eq 1 ]]; then
    echo '安装未完成，恢复之前的服务版本。' >&2
    systemctl stop "$SERVICE" >/dev/null 2>&1
    [[ $old_enabled -eq 1 ]] || systemctl disable "$SERVICE" >/dev/null 2>&1
    if [[ -n "$old_release" && -d "$old_release" ]]; then
      switch_release "$old_release"
    else
      rm -f "$APP_DIR/current"
    fi
    if [[ $had_unit -eq 1 ]]; then cp -a "$work/previous.service" "$UNIT_FILE"; else rm -f "$UNIT_FILE"; fi
    [[ $had_env -eq 1 ]] || rm -f "$ENV_FILE"
    systemctl daemon-reload
    [[ $old_enabled -eq 0 ]] || systemctl enable "$SERVICE" >/dev/null 2>&1
    if [[ $old_active -eq 1 ]]; then
      systemctl restart "$SERVICE" || echo '旧版本未能恢复，请查看 journalctl -u wxchat-message。' >&2
    fi
  fi
  if [[ $success -eq 0 && -n "$release" && "$release" != "$old_release" ]]; then rm -rf -- "$release"; fi
  rm -f "$APP_DIR/.current-install-$$"
  rm -rf -- "$work"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo '[1/7] 安装系统依赖'
packages=(ca-certificates python3 python3-venv)
nginx_bin="$(command -v nginx || true)"
if [[ -z "$nginx_bin" && -x /usr/sbin/nginx ]]; then nginx_bin=/usr/sbin/nginx; fi
if [[ -z "$nginx_bin" ]]; then
  [[ "$(systemctl show nginx.service -p LoadState --value 2>/dev/null || true)" != loaded ]] || die '已有 nginx.service，但找不到可执行文件，请先修复现有 Nginx。'
  packages+=(nginx)
  new_nginx=1
  policy_work="$(mktemp -d /usr/sbin/.wxchat-policy.XXXXXX)"
  if [[ -e /usr/sbin/policy-rc.d || -L /usr/sbin/policy-rc.d ]]; then
    cp -a /usr/sbin/policy-rc.d "$policy_work/policy.original"
    cp -L /usr/sbin/policy-rc.d "$policy_work/policy.delegate"
    chmod 755 "$policy_work/policy.delegate"
    policy_saved=1
  fi
  policy_active=1
  rm -f /usr/sbin/policy-rc.d
  cat > /usr/sbin/policy-rc.d <<EOF
#!/bin/sh
case "\${1:-}" in nginx|nginx.service) exit 101 ;; esac
if [ -x "$policy_work/policy.delegate" ]; then exec "$policy_work/policy.delegate" "\$@"; fi
exit 0
EOF
  chmod 755 /usr/sbin/policy-rc.d
fi
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
apt-get update -qq
apt-get install -y -qq --no-install-recommends "${packages[@]}"
restore_policy
if [[ $new_nginx -eq 1 ]]; then systemctl disable nginx.service >/dev/null; fi
nginx_bin="$(command -v nginx || true)"
[[ -n "$nginx_bin" ]] || nginx_bin=/usr/sbin/nginx
python3 -c 'import sys; assert sys.version_info >= (3, 10), "需要 Python 3.10+，请使用 Debian 12+ 或 Ubuntu 22.04+"'

echo '[2/7] 校验配置和端口'
python3 "$SCRIPT_DIR/installer.py" validate --nginx "$nginx_bin"

echo '[3/7] 备份账号和配置'
backup_dir="$(python3 "$SCRIPT_DIR/installer.py" backup)"
echo "备份目录：$backup_dir"
install -d -m 755 "$APP_DIR" "$APP_DIR/releases"
printf '%s\n' 'WxChat-Message' > "$APP_DIR/.wxchat-message-install"
release="$(mktemp -d "$APP_DIR/releases/$(date -u +%Y%m%d-%H%M%S)-XXXXXX")"
chmod 755 "$release"
for file in app.py proxy.py requirements.lock requirements.txt README.md LICENSE; do cp "$SOURCE_DIR/$file" "$release/"; done
cp -a "$SOURCE_DIR/static" "$SOURCE_DIR/scripts" "$SOURCE_DIR/deploy" "$release/"
printf '%s\n' "${WXCHAT_VERSION:-local-source}" > "$release/INSTALL_SOURCE"

echo '[4/7] 创建独立 Python 环境并校验程序'
python3 -m venv "$release/.venv"
"$release/.venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir -q -r "$release/requirements.lock"
NGINX_BIN="$nginx_bin" "$release/.venv/bin/python" "$SCRIPT_DIR/installer.py" smoke "$release"
chmod -R u=rwX,go=rX "$release"

echo '[5/7] 初始化专用账号和数据目录'
getent group "$SERVICE_USER" >/dev/null || groupadd --system "$SERVICE_USER"
getent passwd "$SERVICE_USER" >/dev/null || useradd --system --gid "$SERVICE_USER" --home-dir "$DATA_DIR" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
[[ "$(id -u "$SERVICE_USER")" -ne 0 ]] || die '服务账号不能是 root。'
python3 "$SCRIPT_DIR/installer.py" initialize --nginx "$nginx_bin"
chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
chmod 700 "$DATA_DIR"
chmod 600 "$ENV_FILE"

echo '[6/7] 切换版本并启动 systemd 服务'
switched=1
systemctl stop "$SERVICE" 2>/dev/null || true
switch_release "$release"
install -m 644 "$SOURCE_DIR/deploy/wxchat-message.service" "$UNIT_FILE"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

echo '[7/7] 检查服务和代理状态'
systemctl is-active --quiet "$SERVICE"
python3 "$SCRIPT_DIR/installer.py" verify
success=1
python3 "$SCRIPT_DIR/installer.py" prune "$old_release"
echo '安装完成。再次运行同一安装命令可升级，账号、端口和配置会保留。'
echo "备份：$backup_dir"
echo '状态：systemctl status wxchat-message'
echo '日志：journalctl -u wxchat-message -n 100 --no-pager'
