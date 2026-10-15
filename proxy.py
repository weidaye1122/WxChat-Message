"""Own an isolated Nginx instance; never edit a system Nginx configuration."""
import collections
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import ssl
import subprocess
import threading
import time
import urllib.request
import urllib.parse


class ProxyError(Exception):
    pass


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def nginx_string(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


class ProxyManager:
    def __init__(self, directory, admin_port=7081, upstream=None, binary=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.lock = threading.RLock()
        self.admin_port = admin_port
        self.upstream = upstream or "https://qyapi.weixin.qq.com"
        parsed = urllib.parse.urlsplit(self.upstream)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or "@" in parsed.netloc or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("上游地址必须是 HTTP(S) 服务地址")
        self.upstream = self.upstream.rstrip("/")
        self.host = os.environ.get("WXCHAT_PROXY_HOST", "127.0.0.1")
        if self.host not in ("127.0.0.1", "0.0.0.0"):
            raise ValueError("代理监听地址仅支持 127.0.0.1 或 0.0.0.0")
        self.binary = binary or os.environ.get("NGINX_BIN") or shutil.which("nginx")
        for candidate in ("/opt/homebrew/bin/nginx", "/usr/sbin/nginx", "/usr/local/bin/nginx"):
            if not self.binary and Path(candidate).is_file():
                self.binary = candidate
        self.config_path = self.directory / "nginx.conf"
        self.pid_path = self.directory / "nginx.pid"
        self.log_path = self.directory / "requests.jsonl"
        self.error_path = self.directory / "nginx-error.log"
        self.settings_path = self.directory / "settings.json"
        self.error = None
        self.settings = {"port": 30888, "enabled": True, "maxBodyMiB": 1}
        if self.settings_path.exists():
            self.settings.update(json.loads(self.settings_path.read_text()))
        for name in ("body", "proxy", "fastcgi", "uwsgi", "scgi"):
            (self.directory / name).mkdir(exist_ok=True, mode=0o700)

    def owned_pid(self):
        try:
            pid = int(self.pid_path.read_text().strip())
            os.kill(pid, 0)
            result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=3)
            if "nginx: master process" in result.stdout and str(self.config_path) in result.stdout:
                return pid
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return None

    def check_health(self, port, maximum=None):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/__wxchat_health" % port, timeout=0.4) as response:
                expected = "wxchat-message-ready:%d:%d" % (port, maximum if maximum is not None else self.settings["maxBodyMiB"])
                return response.status == 200 and response.read() == expected.encode()
        except OSError:
            return False

    def wait_ready(self, port, maximum):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if self.owned_pid() and self.check_health(port, maximum):
                return
            time.sleep(0.08)
        raise ProxyError("代理未能启动，请检查端口是否被占用")

    def render(self, settings):
        trusted = ssl.get_default_verify_paths().cafile
        for candidate in ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem", "/opt/homebrew/etc/ca-certificates/cert.pem"):
            if not trusted and Path(candidate).is_file():
                trusted = candidate
        if not trusted:
            raise ProxyError("缺少系统 CA 证书，请先安装 ca-certificates")
        return "\n".join([
            "worker_processes 1;", "worker_shutdown_timeout 8s;",
            "pid %s;" % nginx_string(self.pid_path),
            "error_log %s warn;" % nginx_string(self.error_path),
            "events { worker_connections 512; }", "http {", "  error_log /dev/null crit;",
            "  server_tokens off;", "  default_type application/octet-stream;",
            "  client_max_body_size %dm;" % settings["maxBodyMiB"], "  sendfile on;", "  tcp_nopush on;",
            *["  %s_temp_path %s;" % (directive, nginx_string(self.directory / name)) for directive, name in
              (("client_body", "body"), ("proxy", "proxy"), ("fastcgi", "fastcgi"), ("uwsgi", "uwsgi"), ("scgi", "scgi"))],
            "  log_format requests escape=json '{\"time\":\"$time_iso8601\",\"method\":\"$request_method\",\"path\":\"$uri\",\"status\":$status,\"seconds\":$request_time,\"bytes\":$body_bytes_sent,\"client\":\"$remote_addr\"}';",
            "  access_log off;", "  server {",
            "    listen %s:%d;" % (self.host, settings["port"]),
            "    location = /__wxchat_health { default_type text/plain; return 200 'wxchat-message-ready:%d:%d'; }" % (settings["port"], settings["maxBodyMiB"]),
            "    location = / { default_type text/html; return 200 '<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><title>WxChat-Message</title><body><h1>WxChat-Message</h1><p>企业微信代理已就绪</p></body></html>'; }",
            "    location / { return 404; }", "    location /cgi-bin {",
            "      access_log %s requests;" % nginx_string(self.log_path),
            "      proxy_pass %s;" % nginx_string(self.upstream),
            "      proxy_http_version 1.0;", "      proxy_set_header Host $proxy_host;",
            "      proxy_set_header Connection close;", "      proxy_ssl_server_name on;",
            "      proxy_ssl_verify on;", "      proxy_ssl_trusted_certificate %s;" % nginx_string(trusted),
            "      proxy_connect_timeout 10s;", "      proxy_read_timeout 60s;",
            "    }", "  }", "}", "",
        ])

    def run_nginx(self, *arguments):
        if not self.binary:
            raise ProxyError("未找到 Nginx。macOS 请执行 brew install nginx；Debian/Ubuntu 请安装 nginx")
        try:
            result = subprocess.run([self.binary, "-p", str(self.directory) + "/", "-c", str(self.config_path), "-e", str(self.error_path), *arguments], capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as error:
            raise ProxyError("无法运行 Nginx，请检查本机安装") from error
        if result.returncode:
            # Validation output contains no user request credentials.
            raise ProxyError("Nginx 配置校验失败：" + result.stderr.strip()[-500:])

    def apply(self, settings):
        with self.lock:
            settings = {"port": settings.get("port"), "enabled": settings.get("enabled"),
                        "maxBodyMiB": settings.get("maxBodyMiB", self.settings["maxBodyMiB"])}
            port = settings.get("port")
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ProxyError("端口必须是 1–65535 之间的整数")
            if port == self.admin_port:
                raise ProxyError("代理端口不能与管理端口相同")
            if not isinstance(settings.get("enabled"), bool):
                raise ProxyError("启用状态无效")
            maximum = settings["maxBodyMiB"]
            if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 100:
                raise ProxyError("上传大小上限必须是 1–100 MiB 之间的整数")
            current = dict(self.settings)
            previous = self.config_path.read_text() if self.config_path.exists() else None
            pid = self.owned_pid()
            if settings["enabled"] and (not pid or port != current["port"]):
                try:
                    with socket.socket() as sock:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind((self.host, port))
                except OSError as error:
                    raise ProxyError("端口 %d 已被占用或没有监听权限" % port) from error
            self.config_path.write_text(self.render(settings))
            os.chmod(self.config_path, 0o600)
            try:
                self.run_nginx("-t")
                if settings["enabled"]:
                    if pid:
                        os.kill(pid, signal.SIGHUP)
                    else:
                        self.run_nginx()
                    self.wait_ready(port, settings["maxBodyMiB"])
                else:
                    self.stop()
                atomic_json(self.settings_path, settings)
                self.settings = dict(settings)
                self.error = None
            except Exception as error:
                if previous is not None:
                    self.config_path.write_text(previous)
                    if pid and self.owned_pid():
                        os.kill(pid, signal.SIGHUP)
                    elif not pid:
                        self.stop()
                else:
                    self.stop()
                self.settings = current
                self.error = str(error)
                if isinstance(error, ProxyError):
                    raise
                raise ProxyError("应用设置失败，已恢复原配置") from error

    def start(self):
        try:
            self.apply(dict(self.settings))
        except ProxyError as error:
            self.error = str(error)

    def stop(self):
        with self.lock:
            pid = self.owned_pid()
            if not pid:
                return
            os.kill(pid, signal.SIGQUIT)
            deadline = time.monotonic() + 9
            while self.owned_pid() and time.monotonic() < deadline:
                time.sleep(0.05)
            if self.owned_pid():
                os.kill(pid, signal.SIGTERM)

    def status(self):
        return {"running": bool(self.owned_pid()) and self.check_health(self.settings["port"]),
                "nginxAvailable": bool(self.binary), "error": self.error,
                "port": self.settings["port"], "enabled": self.settings["enabled"],
                "maxBodyMiB": self.settings["maxBodyMiB"],
                "listenHost": self.host, "upstream": self.upstream}

    def rotate_logs(self):
        with self.lock:
            for path in (self.log_path, self.error_path):
                if path.exists() and path.stat().st_size >= 5 * 1024 * 1024:
                    for number in (3, 2, 1):
                        source = path if number == 1 else Path(str(path) + ".%d" % (number - 1))
                        target = Path(str(path) + ".%d" % number)
                        if source.exists():
                            os.replace(source, target)
                    if self.owned_pid():
                        os.kill(self.owned_pid(), signal.SIGUSR1)

    @staticmethod
    def tail(path, limit):
        if not path.exists():
            return []
        chunks = []
        with open(path, "rb") as handle:
            position = handle.seek(0, 2)
            count = 0
            while position and count <= limit:
                length = min(position, 16384)
                position -= length
                handle.seek(position)
                block = handle.read(length)
                chunks.insert(0, block)
                count += block.count(b"\n")
        return b"".join(chunks).splitlines()[-limit:]

    def logs(self, search="", status="all", limit=200):
        with self.lock:
            records = collections.deque(maxlen=2000)
            for path in [Path(str(self.log_path) + ".%d" % n) for n in (3, 2, 1)] + [self.log_path]:
                for raw in self.tail(path, 2000):
                    try:
                        record = json.loads(raw)
                        # Only allow known fields to leave the server.
                        record = {k: record[k] for k in ("time", "method", "path", "status", "seconds", "bytes", "client")}
                        record["durationMs"] = round(float(record.pop("seconds")) * 1000, 1)
                        record["path"] = str(record["path"]).split("?", 1)[0]
                        records.append(record)
                    except (ValueError, KeyError, TypeError):
                        continue
            items = list(records)
            stats = {"requests": len(items), "errors": sum(r["status"] >= 400 for r in items),
                     "averageMs": round(sum(r["durationMs"] for r in items) / len(items), 1) if items else 0}
            filtered = [r for r in reversed(items) if (not search or search.lower() in (r["path"] + " " + r["method"]).lower()) and
                        (status == "all" or (status == "error" and r["status"] >= 400) or (status == "success" and r["status"] < 400))]
            return {"items": filtered[:limit], "matched": len(filtered), "stats": stats}

    def clear_logs(self):
        with self.lock:
            self.log_path.write_text("")
            for n in (1, 2, 3):
                Path(str(self.log_path) + ".%d" % n).unlink(missing_ok=True)
