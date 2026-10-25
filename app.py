"""Administration for WxChat-Message's native Nginx proxy."""
import argparse
import atexit
import collections
import fcntl
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import threading
import time

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import HTTPException

from proxy import ProxyError, ProxyManager, atomic_json

ROOT = Path(__file__).resolve().parent


def create_app(data_directory=None, admin_port=7081, upstream=None):
    setup_addresses = {ipaddress.ip_address(value.strip()) for value in
                       os.environ.get("WXCHAT_SETUP_ALLOWED_IPS", "").split(",") if value.strip()}
    app = Flask(__name__, static_folder=str(ROOT / "static"), static_url_path="/static")
    data = Path(data_directory or os.environ.get("WXCHAT_DATA", ROOT / ".data")).resolve()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(data, 0o700)
    secret_file = data / "session-key"
    if not secret_file.exists():
        try:
            with open(secret_file, "x") as handle:
                os.chmod(secret_file, 0o600)
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    app.config.update(SECRET_KEY=secret_file.read_text().strip(), MAX_CONTENT_LENGTH=16384,
                      SESSION_COOKIE_NAME=f"wxchat_message_session_{admin_port}", SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=os.environ.get("WXCHAT_SECURE_COOKIE") == "1",
                      PERMANENT_SESSION_LIFETIME=43200)
    auth_file = data / "auth.json"
    manager = ProxyManager(data / "proxy", admin_port=admin_port, upstream=upstream)
    app.extensions["proxy"] = manager
    app.extensions["data_directory"] = data
    auth_lock = threading.RLock()
    failures = collections.defaultdict(list)

    def auth():
        return json.loads(auth_file.read_text()) if auth_file.exists() else None

    def authenticated():
        account = auth()
        return bool(account and session.get("user") == account["username"] and session.get("epoch") == account["epoch"])

    def sign_in(account):
        session.clear()
        session["user"] = account["username"]
        session["epoch"] = account["epoch"]
        session["csrf"] = secrets.token_urlsafe(32)
        session.permanent = True

    @app.before_request
    def protect():
        if not request.path.startswith("/api/"):
            return None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                return jsonify(error="请求来源不匹配，请刷新页面重试"), 403
            provided = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf", "")
            if not expected or not hmac.compare_digest(provided, expected):
                return jsonify(error="页面验证已失效，请刷新后重试"), 403
            if request.path not in ("/api/auth/logout", "/api/logs") and not isinstance(request.get_json(silent=True), dict):
                return jsonify(error="请求内容必须是 JSON 对象"), 400
        if request.path not in ("/api/auth/state", "/api/auth/setup", "/api/auth/login") and not authenticated():
            return jsonify(error="请先登录"), 401

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error="请求体过大" if error.code == 413 else error.description), error.code

    @app.get("/")
    def index():
        return send_from_directory(ROOT / "static", "index.html")

    @app.get("/api/auth/state")
    def auth_state():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        return jsonify(setupRequired=auth() is None, authenticated=authenticated(),
                       username=session.get("user") if authenticated() else None, csrfToken=session["csrf"])

    @app.post("/api/auth/setup")
    def setup():
        with auth_lock:
            if auth() is not None:
                return jsonify(error="管理员已设置，请登录"), 409
            address = ipaddress.ip_address(request.remote_addr)
            if not address.is_loopback and address not in setup_addresses:
                return jsonify(error="首次设置请使用安装时的网络，或在服务器设置 WXCHAT_SETUP_ALLOWED_IPS 后重启服务"), 403
            payload = request.get_json()
            username, password = payload.get("username", ""), payload.get("password", "")
            if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
                return jsonify(error="账号需为 3–32 位字母、数字或 _ . -"), 400
            if not isinstance(password, str) or not 8 <= len(password) <= 128:
                return jsonify(error="密码长度需为 8–128 位"), 400
            if password != payload.get("confirmPassword"):
                return jsonify(error="两次输入的密码不一致"), 400
            account = {"username": username, "passwordHash": generate_password_hash(password, method="scrypt:16384:8:1"), "epoch": secrets.token_hex(16)}
            atomic_json(auth_file, account)
            sign_in(account)
            manager.start()
            return jsonify(ok=True, csrfToken=session["csrf"], proxy=manager.status())

    @app.post("/api/auth/login")
    def login():
        with auth_lock:
            account = auth()
            if not account:
                return jsonify(error="请先设置管理员账号"), 409
            ip = request.remote_addr
            now = time.monotonic()
            failures[ip] = [t for t in failures[ip] if t > now - 900]
            if len(failures[ip]) >= 8:
                return jsonify(error="尝试次数过多，请 15 分钟后重试"), 429
            payload = request.get_json()
            password, username = payload.get("password", ""), payload.get("username", "")
            if not isinstance(password, str) or not isinstance(username, str) or len(password) > 128:
                return jsonify(error="账号或密码不正确"), 401
            valid = check_password_hash(account["passwordHash"], password)
            if not valid or not hmac.compare_digest(username.encode(), account["username"].encode()):
                failures[ip].append(now)
                return jsonify(error="账号或密码不正确"), 401
            failures.pop(ip, None)
            sign_in(account)
            return jsonify(ok=True, csrfToken=session["csrf"])

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/overview")
    def overview():
        return jsonify(name="WxChat-Message", version="0.1.0", username=session["user"],
                       proxy=manager.status(), logs=manager.logs(limit=8))

    @app.get("/api/settings")
    def settings():
        return jsonify(proxy=manager.status(), adminPort=admin_port)

    @app.put("/api/settings")
    def save_settings():
        payload = request.get_json()
        try:
            manager.apply({"port": payload.get("port"), "enabled": payload.get("enabled"),
                           "maxBodyMiB": payload.get("maxBodyMiB", manager.settings["maxBodyMiB"]),
                           "maxLogEntries": payload.get("maxLogEntries", manager.settings["maxLogEntries"])})
        except ProxyError as error:
            return jsonify(error=str(error)), 400
        return jsonify(ok=True, proxy=manager.status())

    @app.get("/api/logs")
    def logs():
        query = request.args.get("search", "")[:200]
        status = request.args.get("status", "all")
        if status not in ("all", "success", "error"):
            return jsonify(error="日志筛选条件无效"), 400
        try:
            offset = int(request.args.get("offset", "0"))
            if not 0 <= offset <= 100000:
                raise ValueError
        except ValueError:
            return jsonify(error="日志页码无效"), 400
        return jsonify(manager.logs(search=query, status=status, offset=offset))

    @app.delete("/api/logs")
    def clear_logs():
        manager.clear_logs()
        return jsonify(ok=True)

    app.extensions["initialized"] = lambda: auth() is not None
    return app


def main():
    parser = argparse.ArgumentParser(description="WxChat-Message 企业微信代理管理面板")
    parser.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default=os.environ.get("WXCHAT_ADMIN_HOST", "0.0.0.0"), help="管理页面监听地址，默认 0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("WXCHAT_ADMIN_PORT", "7081")), help="管理页面端口，默认 7081")
    parser.add_argument("--data", default=os.environ.get("WXCHAT_DATA"), help="独立数据目录")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口范围为 1–65535")
    if args.host not in ("127.0.0.1", "0.0.0.0"):
        parser.error("管理监听地址仅支持 127.0.0.1 或 0.0.0.0")
    app = create_app(args.data, admin_port=args.port, upstream=os.environ.get("WXCHAT_UPSTREAM"))
    data = app.extensions["data_directory"]
    lockfile = open(data / "instance.lock", "a")
    try:
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("该数据目录已有运行实例，请先停止旧实例或使用 --data")
    proxy = app.extensions["proxy"]
    if app.extensions["initialized"]():
        proxy.start()
    closing = threading.Event()

    def maintenance():
        while not closing.wait(10):
            try:
                proxy.rotate_logs()
            except OSError:
                app.logger.exception("日志轮转失败")

    def shutdown(*_):
        closing.set()
        proxy.stop()

    atexit.register(shutdown)

    def signal_shutdown(*_):
        shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, signal_shutdown)
    signal.signal(signal.SIGINT, signal_shutdown)
    threading.Thread(target=maintenance, daemon=True).start()
    from waitress import serve
    print("WxChat-Message 管理监听：%s:%d" % (args.host, args.port), flush=True)
    print("首次访问时设置管理员账号和密码。", flush=True)
    try:
        serve(app, host=args.host, port=args.port, threads=4, ident="WxChat-Message", max_request_body_size=16384)
    finally:
        shutdown()
        lockfile.close()


if __name__ == "__main__":
    main()
