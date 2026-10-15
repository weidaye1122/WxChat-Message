#!/usr/bin/env python3
"""Short-lived installation helpers; never imported by the running service."""
import argparse
import datetime
import http.client
import importlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time

APP = Path('/opt/wxchat-message')
DATA = Path('/var/lib/wxchat-message')
ENV = Path('/etc/wxchat-message.env')
UNIT = Path('/etc/systemd/system/wxchat-message.service')
BACKUPS = Path('/var/backups/wxchat-message')


def environment():
    values = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, separator, value = line.partition('=')
            if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                raise ValueError('环境文件格式无效，请使用 KEY=VALUE 格式')
            parsed = shlex.split(value)
            if len(parsed) > 1:
                raise ValueError('环境文件中的空格值需要引号')
            values[key] = parsed[0] if parsed else ''
    else:
        values = {'WXCHAT_ADMIN_PORT': os.environ.get('WXCHAT_ADMIN_PORT', '7081'),
                  'WXCHAT_DATA': str(DATA), 'NGINX_BIN': os.environ.get('NGINX_BIN', '/usr/sbin/nginx'),
                  'WXCHAT_PROXY_HOST': os.environ.get('WXCHAT_PROXY_HOST', '0.0.0.0')}
    if values.get('WXCHAT_DATA', str(DATA)) != str(DATA):
        raise ValueError(f'安装版数据目录必须为 {DATA}')
    return values


def settings():
    path = DATA / 'proxy/settings.json'
    return json.loads(path.read_text()) if path.exists() else {
        'port': int(os.environ.get('WXCHAT_PROXY_PORT', '30888')), 'enabled': True, 'maxBodyMiB': 1}


def validate(binary):
    values, proxy = environment(), settings()
    admin = int(values.get('WXCHAT_ADMIN_PORT', '7081'))
    port = proxy['port']
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535 or not 1 <= admin <= 65535 or port == admin:
        raise ValueError('管理端口和代理端口须为不同的 1–65535 整数')
    maximum = proxy.get('maxBodyMiB', 1)
    if not isinstance(proxy.get('enabled'), bool) or isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 100:
        raise ValueError('代理启用状态或上传大小设置无效')
    host = values.get('WXCHAT_PROXY_HOST', '127.0.0.1')
    if host not in ('127.0.0.1', '0.0.0.0'):
        raise ValueError('代理监听地址仅支持 127.0.0.1 或 0.0.0.0')
    nginx = values.get('NGINX_BIN', binary) if ENV.exists() else binary
    if not Path(nginx).is_file() or not os.access(nginx, os.X_OK):
        raise ValueError(f'Nginx 不可执行：{nginx}')
    allowed = set()
    control = subprocess.run(['systemctl', 'show', 'wxchat-message.service', '-p', 'ControlGroup', '--value'], capture_output=True, text=True)
    group = control.stdout.strip()
    if group.startswith('/system.slice/wxchat-message.service'):
        path = Path('/sys/fs/cgroup') / group.lstrip('/') / 'cgroup.procs'
        if path.exists():
            allowed = set(map(int, path.read_text().split()))
    for address, number in [('127.0.0.1', admin), (host, port)]:
        try:
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((address, number))
        except OSError as error:
            result = subprocess.run(['ss', '-H', '-lntp', f'sport = :{number}'], capture_output=True, text=True)
            owners = set(map(int, re.findall(r'pid=(\d+)', result.stdout)))
            if not owners or not owners.issubset(allowed):
                raise ValueError(f'端口 {number} 已被其他服务占用，未停止或修改该服务。首次安装可设置 WXCHAT_ADMIN_PORT / WXCHAT_PROXY_PORT 选择其他端口。') from error
    return values, proxy


def initialize(binary):
    values, proxy = environment(), settings()
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    (DATA / 'proxy').mkdir(mode=0o700, exist_ok=True)
    if not (DATA / 'proxy/settings.json').exists():
        (DATA / 'proxy/settings.json').write_text(json.dumps(proxy, indent=2) + '\n')
        os.chmod(DATA / 'proxy/settings.json', 0o600)
    if not ENV.exists():
        values['NGINX_BIN'] = binary
        with ENV.open('x') as handle:
            os.chmod(ENV, 0o600)
            handle.write(''.join(f'{key}={shlex.quote(value)}\n' for key, value in values.items()))


def backup():
    BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-')
    destination = Path(tempfile.mkdtemp(prefix=stamp, dir=BACKUPS))
    paths = [(DATA / name, destination / 'data' / name) for name in ['auth.json', 'session-key', 'proxy/settings.json']]
    paths += [(ENV, destination / 'wxchat-message.env'), (UNIT, destination / 'wxchat-message.service')]
    for source, target in paths:
        if source.is_file():
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copy2(source, target)
            os.chmod(target, 0o600)
    current = str((APP / 'current').resolve()) if (APP / 'current').exists() else None
    (destination / 'backup.json').write_text(json.dumps({'currentRelease': current, 'dataDirectory': str(DATA)}, indent=2) + '\n')
    os.chmod(destination / 'backup.json', 0o600)
    print(destination)


def smoke(release):
    importlib.import_module('flask')
    importlib.import_module('waitress')
    sys.path.insert(0, str(Path(release).resolve()))
    from app import create_app
    with tempfile.TemporaryDirectory(prefix='wxchat-install-check-') as temporary:
        app = create_app(temporary)
        assert app.test_client().get('/api/auth/state').json['setupRequired']
        proxy = app.extensions['proxy']
        proxy.apply({'port': 30888, 'enabled': False, 'maxBodyMiB': 1})


def fetch(port, path):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def verify():
    values, proxy = environment(), settings()
    admin = int(values.get('WXCHAT_ADMIN_PORT', '7081'))
    last = None
    for _ in range(30):
        try:
            status, body = fetch(admin, '/api/auth/state')
            assert status == 200
            state = json.loads(body)
            assert state['setupRequired'] == (not (DATA / 'auth.json').exists())
            if not state['setupRequired'] and proxy['enabled']:
                status, body = fetch(proxy['port'], '/__wxchat_health')
                assert status == 200 and body.decode() == f"wxchat-message-ready:{proxy['port']}:{proxy['maxBodyMiB']}"
            print(f'管理页面：http://127.0.0.1:{admin}')
            print(f"代理地址：{values.get('WXCHAT_PROXY_HOST', '127.0.0.1')}:{proxy['port']}")
            if state['setupRequired']:
                print('首次设置管理员后代理才会启动；请通过 SSH 隧道访问管理页面。')
            return
        except (OSError, ValueError, AssertionError) as error:
            last = error
            time.sleep(0.5)
    raise ValueError(f'服务健康检查未通过：{last}')


def prune(previous):
    keep = {(APP / 'current').resolve()}
    if previous:
        keep.add(Path(previous).resolve())
    for path in (APP / 'releases').iterdir():
        if path.is_dir() and not path.is_symlink() and path.resolve() not in keep and re.fullmatch(r'\d{8}-\d{6}-[A-Za-z0-9]+', path.name):
            shutil.rmtree(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='action', required=True)
    for name in ['validate', 'initialize']:
        commands.add_parser(name).add_argument('--nginx', required=True)
    commands.add_parser('backup')
    commands.add_parser('verify')
    commands.add_parser('smoke').add_argument('release')
    commands.add_parser('prune').add_argument('previous')
    args = parser.parse_args()
    try:
        if args.action == 'validate': validate(args.nginx)
        elif args.action == 'initialize': initialize(args.nginx)
        elif args.action == 'backup': backup()
        elif args.action == 'verify': verify()
        elif args.action == 'smoke': smoke(args.release)
        elif args.action == 'prune': prune(args.previous)
    except (ValueError, KeyError, OSError, AssertionError) as error:
        print(f'错误：{error}', file=sys.stderr)
        sys.exit(1)
