#!/usr/bin/env python3
"""Real apt/systemd installation in a disposable local container only."""
import hashlib
import http.client
from http.cookies import SimpleCookie
import http.server
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import time

assert Path('/.dockerenv').exists() and Path('/src/tests/installer/Dockerfile').exists()
SOURCE = Path('/src')
APP = Path('/opt/wxchat-message')
DATA = Path('/var/lib/wxchat-message')
ENV = Path('/etc/wxchat-message.env')
completed = []
container_ip = socket.gethostbyname(socket.gethostname())


def run(args, success=True, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=240, **kwargs)
    if success != (result.returncode == 0):
        print(result.stdout, result.stderr, flush=True)
        raise AssertionError((args, result.returncode))
    return result


def check(label):
    completed.append(label)
    print('PASS: ' + label, flush=True)


def request(port, path, method='GET', body=None, headers=None, host='127.0.0.1'):
    connection = http.client.HTTPConnection(host, port, timeout=10)
    try:
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        return response.status, response.getheaders(), response.read()
    finally:
        connection.close()


def service_pid(name):
    return int(run(['systemctl', 'show', name, '-p', 'MainPID', '--value']).stdout)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


archive_bytes = io.BytesIO()
with tarfile.open(fileobj=archive_bytes, mode='w:gz') as archive:
    for item in SOURCE.iterdir():
        archive.add(item, arcname='WxChat-Message-main/' + item.name)

probe_bytes = io.BytesIO()
with tarfile.open(fileobj=probe_bytes, mode='w:gz') as archive:
    for name, content in {
        'app.py': b'', 'scripts/common.sh': b'',
        'scripts/install.sh': b'printf "%s\\n" "$WXCHAT_VERSION" > "$WXCHAT_TEST_MARKER"\n',
    }.items():
        entry = tarfile.TarInfo('WxChat-Message-probe/' + name)
        entry.size = len(content)
        archive.addfile(entry, io.BytesIO(content))


class Upstream(http.server.BaseHTTPRequestHandler):
    stable_tag = 'v0.1.0-fixture'
    latest_status = 302
    redirect_style = 'absolute'
    archive_missing = False
    paths = []

    def do_GET(self):
        type(self).paths.append(self.path)
        prefix = '/probe' if self.path.startswith('/probe/') else ''
        path = self.path[len(prefix):]
        if path == '/releases/latest':
            self.send_response(self.latest_status)
            if self.latest_status == 302:
                target = prefix + '/releases/tag/' + self.stable_tag
                if self.redirect_style == 'absolute':
                    target = f'http://127.0.0.1:{self.server.server_port}' + target
                elif self.redirect_style == 'relative-path':
                    target = 'tag/' + self.stable_tag
                elif self.redirect_style == 'foreign':
                    target = '/unrelated/releases/tag/' + self.stable_tag
                elif self.redirect_style == 'invalid':
                    target = prefix + '/releases/tag/bad%20tag'
                self.send_header('Location', target)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if path.startswith('/archive/'):
            ref = path.removeprefix('/archive/').removesuffix('.tar.gz')
            if self.archive_missing or ref not in {'refs/tags/' + self.stable_tag, 'v0.0.9', 'main', 'codex/check', 'f' * 40}:
                self.send_error(404)
                return
            body = (probe_bytes if prefix else archive_bytes).getvalue()
        else:
            body = json.dumps({'path': self.path, 'method': 'GET'}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        payload = json.dumps({'path': self.path, 'sha256': hashlib.sha256(body).hexdigest()}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
upstream.daemon_threads = True
threading.Thread(target=upstream.serve_forever, daemon=True).start()


def bootstrap(success=True, **extra):
    env = dict(os.environ, WXCHAT_REPO_URL=f'http://127.0.0.1:{upstream.server_port}',
               WXCHAT_ADMIN_PORT='17081', WXCHAT_PROXY_PORT='30889',
               SSH_CONNECTION=f'{container_ip} 50000 {container_ip} 22', **extra)
    if 'WXCHAT_VERSION' not in extra:
        env.pop('WXCHAT_VERSION', None)
    return run(['bash', '/dev/stdin'], success=success, input=(SOURCE / 'install.sh').read_text(), env=env, cwd='/tmp')


# Exercise both download tools without Python/jq in PATH and without running the real installer.
with tempfile.TemporaryDirectory(prefix='wxchat-bootstrap-probe-') as temporary:
    root = Path(temporary)
    scratch = root / 'downloads'
    scratch.mkdir()
    marker = root / 'installed-version'
    for downloader in ['wget', 'curl']:
        binary_dir = root / downloader
        binary_dir.mkdir()
        for command in ['bash', 'dirname', 'mktemp', 'rm', 'mkdir', 'tar', 'gzip', 'awk', downloader]:
            (binary_dir / command).symlink_to(shutil.which(command))

        def probe(version=None, success=True):
            marker.unlink(missing_ok=True)
            Upstream.paths.clear()
            env = dict(os.environ, PATH=str(binary_dir), TMPDIR=str(scratch),
                       WXCHAT_REPO_URL=f'http://127.0.0.1:{upstream.server_port}/probe',
                       WXCHAT_TEST_MARKER=str(marker))
            env.pop('WXCHAT_VERSION', None)
            if version is not None:
                env['WXCHAT_VERSION'] = version
            result = run(['/bin/bash', '/dev/stdin'], success=success,
                         input=(SOURCE / 'install.sh').read_text(), env=env, cwd='/tmp')
            assert not list(scratch.iterdir()), ('bootstrap temporary files leaked', downloader)
            if not success:
                assert not marker.exists(), 'failed lookup must not execute the installer'
            return result

        for style in ['absolute', 'relative-root', 'relative-path']:
            Upstream.redirect_style = style
            probe()
            assert marker.read_text().strip() == Upstream.stable_tag
            assert '/probe/archive/refs/tags/' + Upstream.stable_tag + '.tar.gz' in Upstream.paths
            assert '/probe/archive/main.tar.gz' not in Upstream.paths
        Upstream.redirect_style = 'absolute'
        probe(version='')
        assert marker.read_text().strip() == Upstream.stable_tag

        for ref in ['v0.0.9', 'main', 'codex/check', 'f' * 40]:
            probe(version=ref)
            assert marker.read_text().strip() == ref
            assert Upstream.paths == ['/probe/archive/' + ref + '.tar.gz']

        Upstream.latest_status = 404
        failed = probe(success=False)
        assert '正式 Release' in failed.stderr and 'main' in failed.stderr
        assert all('/archive/' not in path for path in Upstream.paths)
        Upstream.latest_status = 302
        for style in ['foreign', 'invalid']:
            Upstream.redirect_style = style
            probe(success=False)
            assert all('/archive/' not in path for path in Upstream.paths)
        Upstream.redirect_style = 'absolute'
        Upstream.archive_missing = True
        probe(success=False)
        Upstream.archive_missing = False
        probe(version='../main', success=False)
        assert not Upstream.paths
        check(downloader + ' bootstrap selects the stable release, preserves explicit refs and stops safely on failures')
assert not APP.exists()


policy = Path('/usr/sbin/policy-rc.d')
policy_target = Path('/usr/lib/wxchat-test-policy')
shutil.move(policy, policy_target)
policy.symlink_to('../lib/wxchat-test-policy')
policy_before = digest(policy_target)
fakebin = Path('/var/tmp/failing-package-manager')
fakebin.mkdir()
(fakebin / 'apt-get').write_text('#!/bin/sh\nexit 42\n')
(fakebin / 'apt-get').chmod(0o755)
failure_environment = dict(os.environ, PATH=str(fakebin) + ':' + os.environ['PATH'])
resolved = run(['bash', '-c', 'command -v apt-get'], env=failure_environment).stdout.strip()
assert resolved == str(fakebin / 'apt-get'), (resolved, failure_environment['PATH'], (fakebin / 'apt-get').exists(), os.access(fakebin / 'apt-get', os.X_OK), os.getuid(), os.geteuid())
assert run([str(fakebin / 'apt-get')], success=False).returncode == 42
failed = run(['bash', '/src/scripts/install.sh'], success=False, env=failure_environment)
assert failed.returncode == 42
assert policy.is_symlink() and os.readlink(policy) == '../lib/wxchat-test-policy' and digest(policy_target) == policy_before
assert not (APP / 'current').exists()
check('package failure restores the original policy symlink and target')

with socket.socket() as occupied:
    occupied.bind(('0.0.0.0', 30888))
    occupied.listen()
    failed = run(['bash', '/src/scripts/install.sh'], success=False)
    assert '30888' in failed.stderr and occupied.getsockname()[1] == 30888, (failed.stdout, failed.stderr)
assert policy.is_symlink() and digest(policy_target) == policy_before
assert run(['systemctl', 'is-active', 'nginx'], success=False).stdout.strip() == 'inactive'
assert run(['systemctl', 'is-enabled', 'nginx'], success=False).stdout.strip() == 'disabled'
check('busy production proxy port is rejected; package Nginx never starts')

run(['systemctl', 'enable', '--now', 'nginx'])
global_pid = service_pid('nginx')
global_config = digest(Path('/etc/nginx/nginx.conf'))
bootstrap()
assert (APP / 'current/INSTALL_SOURCE').read_text().strip() == Upstream.stable_tag
assert service_pid('nginx') == global_pid
assert digest(Path('/etc/nginx/nginx.conf')) == global_config
assert policy.is_symlink() and digest(policy_target) == policy_before
assert json.loads(request(17081, '/api/auth/state')[2])['setupRequired']
assert 'WXCHAT_ADMIN_HOST=0.0.0.0' in ENV.read_text()
assert f'WXCHAT_SETUP_ALLOWED_IPS={container_ip}' in ENV.read_text()
assert json.loads(request(17081, '/api/auth/state', host=container_ip)[2])['setupRequired']
check('remote-style bootstrap installs with custom ports and preserves existing Nginx')

with ENV.open('a') as handle:
    handle.write(f'WXCHAT_UPSTREAM=http://127.0.0.1:{upstream.server_port}\n')
run(['systemctl', 'restart', 'wxchat-message'])
time.sleep(0.5)
cookies = SimpleCookie()
csrf = ''


def admin(path, method='GET', payload=None):
    global csrf
    headers = {'Content-Type': 'application/json', 'X-CSRF-Token': csrf,
               'Cookie': '; '.join(f'{key}={value.value}' for key, value in cookies.items())}
    status, response_headers, body = request(17081, path, method, json.dumps(payload).encode() if payload is not None else None, headers, host=container_ip)
    for key, value in response_headers:
        if key.lower() == 'set-cookie': cookies.load(value)
    result = json.loads(body)
    assert status == 200, (path, status, result)
    if result.get('csrfToken'): csrf = result['csrfToken']
    return result


admin('/api/auth/state')
setup = admin('/api/auth/setup', 'POST', {'username': 'installer-admin', 'password': 'disposable-installer-fixture-12345', 'confirmPassword': 'disposable-installer-fixture-12345'})
assert setup['proxy']['running'], setup
assert setup['proxy']['maxLogEntries'] == 200
pid = service_pid('wxchat-message')
assert Path(f'/proc/{pid}/status').read_text().split('Uid:', 1)[1].split()[0] != '0'
assert DATA.stat().st_mode & 0o777 == 0o700 and (DATA / 'auth.json').stat().st_mode & 0o777 == 0o600
assert json.loads(request(30889, '/cgi-bin/gettoken?x=a%2Fb')[2])['path'] == '/cgi-bin/gettoken?x=a%2Fb'
admin('/api/settings', 'PUT', {'port': 30890, 'enabled': True, 'maxBodyMiB': 2, 'maxLogEntries': 300})
body = b'--fixture\r\nContent-Disposition: form-data; name="media"; filename="image.jpg"\r\n\r\n' + b'x' * 1048577 + b'\r\n--fixture--\r\n'
status, _, response = request(30890, '/cgi-bin/media/upload?access_token=fixture-only&type=image', 'POST', body, {'Content-Type': 'multipart/form-data; boundary=fixture'})
assert status == 200 and json.loads(response)['sha256'] == hashlib.sha256(body).hexdigest()
assert admin('/api/logs')['items']
check('non-root systemd service supports setup, port changes, multipart uploads and logs')

before = {str(path): digest(path) for path in [DATA / 'auth.json', DATA / 'session-key', DATA / 'proxy/settings.json', ENV]}
old_release = (APP / 'current').resolve()
Upstream.latest_status = 404
running_pid = service_pid('wxchat-message')
bootstrap(success=False)
assert (APP / 'current').resolve() == old_release and service_pid('wxchat-message') == running_pid
assert all(digest(Path(path)) == value for path, value in before.items())
assert admin('/api/auth/state')['authenticated']
assert service_pid('nginx') == global_pid
Upstream.latest_status = 302
check('missing release leaves the existing program, running services, session and settings untouched')

Upstream.stable_tag = 'v0.1.1-fixture'
bootstrap()
assert (APP / 'current').resolve() != old_release
assert (APP / 'current/INSTALL_SOURCE').read_text().strip() == Upstream.stable_tag
assert all(digest(Path(path)) == value for path, value in before.items())
assert admin('/api/auth/state')['authenticated']
assert json.loads(request(30890, '/cgi-bin/gettoken')[2])['method'] == 'GET'
assert service_pid('nginx') == global_pid
check('repeat installation upgrades atomically and preserves account, session and proxy settings')

backup = Path(run(['bash', str(APP / 'current/scripts/backup.sh')]).stdout.strip())
assert (backup / 'data/auth.json').is_file() and (backup / 'wxchat-message.env').is_file()
assert backup.stat().st_mode & 0o777 == 0o700
check('backup includes account, key, settings and environment with private permissions')

good_release = (APP / 'current').resolve()
broken = Path('/tmp/broken-upgrade')
shutil.copytree(SOURCE, broken)
unit = broken / 'deploy/wxchat-message.service'
unit.write_text(unit.read_text().replace('Type=simple', 'Type=exec').replace('ExecStart=/opt/wxchat-message/current/.venv/bin/python /opt/wxchat-message/current/app.py', 'ExecStart=/missing-wxchat-executable'))
run(['bash', str(broken / 'scripts/install.sh')], success=False)
assert (APP / 'current').resolve() == good_release
for _ in range(30):
    try:
        if admin('/api/auth/state')['authenticated']: break
    except OSError: time.sleep(0.2)
else: raise AssertionError('Previous service did not recover')
assert request(30890, '/cgi-bin/gettoken')[0] == 200
assert service_pid('nginx') == global_pid
check('failed service upgrade restores the prior release, unit and running proxy')

suite = run(['runuser', '-u', 'wxchat-message', '--', str(APP / 'current/.venv/bin/python'), '-m', 'unittest', 'discover', '-s', '/src/tests', '-v'], cwd='/src')
assert 'OK' in suite.stderr and 'skipped' not in suite.stderr
check('application and log retention tests pass on Linux')

run(['bash', str(APP / 'current/scripts/uninstall.sh')])
assert not APP.exists() and not Path('/etc/systemd/system/wxchat-message.service').exists()
assert all(digest(Path(path)) == value for path, value in before.items())
for port in [17081, 30890]:
    with socket.socket() as sock: assert sock.connect_ex(('127.0.0.1', port)) != 0
assert service_pid('nginx') == global_pid and digest(Path('/etc/nginx/nginx.conf')) == global_config
check('uninstall removes only this application and keeps data and other Nginx running')

bootstrap()
assert admin('/api/auth/state')['authenticated']
assert request(30890, '/cgi-bin/gettoken')[0] == 200
assert all(digest(Path(path)) == value for path, value in before.items())
run(['bash', str(APP / 'current/scripts/uninstall.sh')])
assert policy.is_symlink() and digest(policy_target) == policy_before
assert service_pid('nginx') == global_pid
check('reinstall reuses the preserved account and settings')
upstream.shutdown()
upstream.server_close()
print(json.dumps({'passed': completed, 'count': len(completed)}, indent=2), flush=True)
