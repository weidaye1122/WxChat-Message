import hashlib
import http.client
import http.server
import json
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from app import create_app


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Upstream(http.server.BaseHTTPRequestHandler):
    def do_request(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        status = 429 if "/rate-limit" in self.path else 200
        payload = json.dumps({"method": self.command, "path": self.path, "sha256": hashlib.sha256(body).hexdigest(),
                              "contentType": self.headers.get("Content-Type"), "custom": self.headers.get("X-Probe")}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Probe-Response", "preserved")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_request

    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which("nginx"), "Real Nginx is required for integration tests")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        cls.upstream.daemon_threads = True
        threading.Thread(target=cls.upstream.serve_forever, daemon=True).start()
        cls.upstream_url = "http://127.0.0.1:%d" % cls.upstream.server_port

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wxchat-integration-")
        self.app = create_app(self.temp.name, admin_port=free_port(), upstream=self.upstream_url)
        self.app.testing = True
        self.proxy = self.app.extensions["proxy"]
        self.proxy.settings["port"] = free_port()
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/auth/state").json["csrfToken"]
        self.password = "integration-fixture-only-12345"

    def tearDown(self):
        self.proxy.stop()
        self.temp.cleanup()

    def call(self, path, method="POST", payload=None, csrf=None):
        response = self.client.open(path, method=method, json=payload, headers={"X-CSRF-Token": self.csrf if csrf is None else csrf})
        if response.is_json and response.json.get("csrfToken"):
            self.csrf = response.json["csrfToken"]
        return response

    def setup_admin(self):
        response = self.call("/api/auth/setup", payload={"username": "testadmin", "password": self.password, "confirmPassword": self.password})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json["proxy"]["running"], response.json)

    def proxy_request(self, path, method="GET", body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.proxy.settings["port"], timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_first_setup_hashes_password_and_disables_repeat_setup(self):
        self.assertTrue(self.client.get("/api/auth/state").json["setupRequired"])
        self.assertEqual(self.client.get("/api/logs").status_code, 401)
        self.setup_admin()
        account = Path(self.temp.name, "auth.json")
        self.assertNotIn(self.password, account.read_text())
        self.assertEqual(account.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.call("/api/auth/setup", payload={}).status_code, 409)
        self.assertTrue(self.client.get("/api/auth/state").json["authenticated"])

    def test_json_request_and_sensitive_log_redaction(self):
        self.setup_admin()
        body = json.dumps({"text": "PRIVATE_MESSAGE_DO_NOT_LOG"}, ensure_ascii=False).encode()
        path = "/cgi-bin/message/send?access_token=SECRET_TOKEN_DO_NOT_LOG&corpsecret=PRIVATE_SECRET"
        status, headers, raw = self.proxy_request(path, "POST", body, {"Content-Type": "application/json", "X-Probe": "preserved"})
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(data["path"], path)
        self.assertEqual(data["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(data["custom"], "preserved")
        self.assertEqual(headers["X-Probe-Response"], "preserved")
        logs = self.client.get("/api/logs").json
        self.assertEqual(logs["items"][0]["path"], "/cgi-bin/message/send")
        for file in self.proxy.directory.glob("*.log"):
            self.assertNotIn("SECRET_TOKEN_DO_NOT_LOG", file.read_text())
        self.assertNotIn("SECRET_TOKEN_DO_NOT_LOG", self.proxy.log_path.read_text())
        self.assertNotIn("PRIVATE_MESSAGE_DO_NOT_LOG", self.proxy.log_path.read_text())

    def test_multipart_image_and_encoded_query_are_unchanged(self):
        self.setup_admin()
        boundary = "wxchat-fixture"
        body = b'--wxchat-fixture\r\nContent-Disposition: form-data; name="media"; filename="test.jpg"\r\nContent-Type: image/jpeg\r\n\r\n' + bytes(range(256)) * 1024 + b"\r\n--wxchat-fixture--\r\n"
        path = "/cgi-bin/media/upload?type=image&x=a%2Fb%26c&x=2"
        status, _, raw = self.proxy_request(path, "POST", body, {"Content-Type": "multipart/form-data; boundary=" + boundary})
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(data["path"], path)
        self.assertEqual(data["sha256"], hashlib.sha256(body).hexdigest())
        self.assertIn(boundary, data["contentType"])

    def test_existing_upload_boundary_and_no_secrets_in_error_log(self):
        self.setup_admin()
        path = "/cgi-bin/media/upload?access_token=ERROR_LOG_MUST_NOT_STORE_THIS"
        self.assertEqual(self.proxy_request(path, "POST", b"x" * 1048576)[0], 200)
        self.assertEqual(self.proxy_request(path, "POST", b"x" * 1048577)[0], 413)
        self.assertNotIn("ERROR_LOG_MUST_NOT_STORE_THIS", self.proxy.error_path.read_text())

    def test_changing_port_applies_and_persists(self):
        self.setup_admin()
        old, new = self.proxy.settings["port"], free_port()
        response = self.call("/api/settings", "PUT", {"port": new, "enabled": True})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(self.proxy.check_health(new))
        deadline = time.monotonic() + 2
        while self.proxy.check_health(old) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(self.proxy.check_health(old))
        self.assertEqual(json.loads(self.proxy.settings_path.read_text())["port"], new)
        self.proxy.stop()
        restarted = create_app(self.temp.name, admin_port=self.proxy.admin_port, upstream=self.upstream_url)
        self.proxy = restarted.extensions["proxy"]
        self.proxy.start()
        self.assertTrue(self.proxy.check_health(new))

    def test_busy_port_preserves_running_proxy_and_settings(self):
        self.setup_admin()
        before = self.proxy.config_path.read_bytes()
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            response = self.call("/api/settings", "PUT", {"port": port, "enabled": True})
        self.assertEqual(response.status_code, 400)
        self.assertIn("占用", response.json["error"])
        self.assertEqual(self.proxy.config_path.read_bytes(), before)
        self.assertTrue(self.proxy.status()["running"])
        self.assertEqual(self.proxy_request("/cgi-bin/gettoken")[0], 200)

    def test_admin_port_and_invalid_ports_are_rejected(self):
        self.setup_admin()
        for port in [0, 65536, "12345", True, self.proxy.admin_port]:
            response = self.call("/api/settings", "PUT", {"port": port, "enabled": True})
            self.assertEqual(response.status_code, 400, port)
        self.assertTrue(self.proxy.status()["running"])

    def test_disable_and_enable_proxy(self):
        self.setup_admin()
        port = self.proxy.settings["port"]
        self.assertEqual(self.call("/api/settings", "PUT", {"port": port, "enabled": False}).status_code, 200)
        self.assertFalse(self.proxy.status()["running"])
        self.assertEqual(self.call("/api/settings", "PUT", {"port": port, "enabled": True}).status_code, 200)
        self.assertTrue(self.proxy.status()["running"])

    def test_upload_limit_can_be_changed_and_persisted(self):
        self.setup_admin()
        port = self.proxy.settings["port"]
        response = self.call("/api/settings", "PUT", {"port": port, "enabled": True, "maxBodyMiB": 2})
        self.assertEqual(response.status_code, 200, response.json)
        # Wait for old workers to drain after an in-place reload.
        deadline = time.monotonic() + 2
        status = 413
        while status == 413 and time.monotonic() < deadline:
            status = self.proxy_request("/cgi-bin/media/upload", "POST", b"x" * 1048577)[0]
            if status == 413:
                time.sleep(0.05)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(self.proxy.settings_path.read_text())["maxBodyMiB"], 2)
        self.assertEqual(self.client.get("/api/settings").json["proxy"]["maxBodyMiB"], 2)

    def test_invalid_upload_limits_preserve_existing_settings(self):
        self.setup_admin()
        for maximum in [0, 101, "2", True, -1]:
            response = self.call("/api/settings", "PUT", {"port": self.proxy.settings["port"], "enabled": True, "maxBodyMiB": maximum})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.proxy.settings["maxBodyMiB"], 1)
        self.assertTrue(self.proxy.status()["running"])

    def test_logs_filter_clear_and_require_login(self):
        self.setup_admin()
        self.proxy_request("/cgi-bin/gettoken")
        self.proxy_request("/cgi-bin/rate-limit")
        logs = self.client.get("/api/logs?status=error").json
        self.assertEqual(logs["matched"], 1)
        self.assertEqual(logs["items"][0]["status"], 429)
        self.assertEqual(logs["stats"]["errors"], 1)
        self.assertEqual(self.client.get("/api/logs?search=gettoken").json["matched"], 1)
        self.assertEqual(self.call("/api/logs", "DELETE").status_code, 200)
        self.assertEqual(self.client.get("/api/logs").json["items"], [])
        self.call("/api/auth/logout")
        self.assertEqual(self.client.get("/api/logs").status_code, 401)

    def test_csrf_and_wrong_origin_do_not_change_settings(self):
        self.setup_admin()
        self.assertEqual(self.call("/api/settings", "PUT", {}, csrf="invalid").status_code, 403)
        response = self.client.put("/api/settings", json={"port": free_port(), "enabled": False}, headers={"X-CSRF-Token": self.csrf, "Origin": "https://different.invalid"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self.proxy.status()["running"])

    def test_logout_and_login(self):
        self.setup_admin()
        self.call("/api/auth/logout")
        self.csrf = self.client.get("/api/auth/state").json["csrfToken"]
        self.assertEqual(self.call("/api/auth/login", payload={"username": "testadmin", "password": "incorrect"}).status_code, 401)
        self.assertEqual(self.call("/api/auth/login", payload={"username": "testadmin", "password": self.password}).status_code, 200)
        self.assertEqual(self.client.get("/api/overview").status_code, 200)

    def test_malformed_json_is_a_validation_error(self):
        response = self.call("/api/auth/setup", payload=["not", "an", "object"])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.app.extensions["initialized"]())

    def test_remote_setup_only_accepts_configured_installation_source(self):
        with patch.dict('os.environ', {'WXCHAT_SETUP_ALLOWED_IPS': '203.0.113.10'}):
            app = create_app(self.temp.name, admin_port=self.proxy.admin_port, upstream=self.upstream_url)
        self.proxy = app.extensions['proxy']
        self.proxy.settings['port'] = free_port()
        client = app.test_client()
        csrf = client.get('/api/auth/state').json['csrfToken']
        payload = {'username': 'testadmin', 'password': self.password, 'confirmPassword': self.password}
        headers = {'X-CSRF-Token': csrf, 'X-Forwarded-For': '203.0.113.10'}
        denied = client.post('/api/auth/setup', json=payload, headers=headers, environ_overrides={'REMOTE_ADDR': '203.0.113.11'})
        self.assertEqual(denied.status_code, 403)
        allowed = client.post('/api/auth/setup', json=payload, headers=headers, environ_overrides={'REMOTE_ADDR': '203.0.113.10'})
        self.assertEqual(allowed.status_code, 200, allowed.json)
        self.assertTrue(allowed.json['proxy']['running'])
        self.assertEqual(client.get('/api/settings').status_code, 200)

    def test_log_retention_validation_persistence_and_pagination(self):
        self.setup_admin()
        settings = {'port': self.proxy.settings['port'], 'enabled': True, 'maxLogEntries': 450}
        self.assertEqual(self.call('/api/settings', 'PUT', settings).status_code, 200)
        for invalid in [0, -1, 100001, '200', True, 2.5, None]:
            response = self.call('/api/settings', 'PUT', dict(settings, maxLogEntries=invalid))
            self.assertEqual(response.status_code, 400, invalid)
        self.assertEqual(json.loads(self.proxy.settings_path.read_text())['maxLogEntries'], 450)
        for number in range(455):
            self.proxy_request('/cgi-bin/retention-%d' % number)
        result = self.client.get('/api/logs?offset=200').json
        self.assertEqual(result['stats']['requests'], 450)
        self.assertEqual(result['maxLogEntries'], 450)
        self.assertEqual(len(result['items']), 200)
        self.assertEqual(result['items'][0]['path'], '/cgi-bin/retention-254')
        for offset in ['-1', 'bad', '100001']:
            self.assertEqual(self.client.get('/api/logs?offset=' + offset).status_code, 400)
        self.proxy.stop()
        app = create_app(self.temp.name, admin_port=self.proxy.admin_port, upstream=self.upstream_url)
        self.proxy = app.extensions['proxy']
        self.assertEqual(self.proxy.settings['maxLogEntries'], 450)

    def test_log_cleanup_while_nginx_keeps_forwarding(self):
        self.setup_admin()
        response = self.call('/api/settings', 'PUT', {'port': self.proxy.settings['port'], 'enabled': True, 'maxLogEntries': 20})
        self.assertEqual(response.status_code, 200)
        failures = []
        def generate():
            try:
                for number in range(100):
                    if self.proxy_request('/cgi-bin/concurrent-%d' % number)[0] != 200:
                        failures.append(number)
            except Exception as error:
                failures.append(str(error))
        writer = threading.Thread(target=generate)
        writer.start()
        while writer.is_alive():
            self.proxy.rotate_logs()
            time.sleep(0.02)
        writer.join()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.proxy.rotate_logs()
            if not self.proxy.pending_log_path.exists():
                break
            time.sleep(0.05)
        self.assertEqual(failures, [])
        actual = [json.loads(line)['path'] for path in self.proxy.request_log_paths() if path.exists() for line in path.read_text().splitlines()]
        self.assertEqual(actual, ['/cgi-bin/concurrent-%d' % number for number in range(80, 100)])
        self.assertEqual(self.proxy_request('/cgi-bin/after-cleanup')[0], 200)
        self.assertEqual(self.client.get('/api/logs').json['items'][0]['path'], '/cgi-bin/after-cleanup')


if __name__ == "__main__":
    unittest.main(verbosity=2)
