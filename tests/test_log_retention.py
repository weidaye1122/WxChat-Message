import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from proxy import ProxyManager


def record(number):
    return json.dumps({'time': '2026-10-25T12:00:00+00:00', 'method': 'GET', 'path': '/cgi-bin/%d' % number,
                       'status': 200, 'seconds': 0.01, 'bytes': 10, 'client': '127.0.0.1'})


class LogRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.proxy = ProxyManager(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, path, first, last):
        path.write_text(''.join(record(number) + '\n' for number in range(first, last)))

    def entries(self):
        return [json.loads(line)['path'] for path in self.proxy.request_log_paths() if path.exists()
                for line in path.read_text().splitlines()]

    def test_legacy_config_defaults_to_200_and_prunes_all_archives(self):
        self.proxy.settings_path.write_text(json.dumps({'port': 30888, 'enabled': False, 'maxBodyMiB': 1}))
        self.proxy = ProxyManager(self.temporary.name)
        self.assertEqual(self.proxy.settings['maxLogEntries'], 200)
        for suffix, first, last in [('.3', 0, 100), ('.2', 100, 200), ('.1', 200, 300)]:
            self.write(Path(str(self.proxy.log_path) + suffix), first, last)
        self.write(self.proxy.log_path, 300, 600)
        self.proxy.rotate_logs()
        self.assertEqual(self.entries(), ['/cgi-bin/%d' % number for number in range(400, 600)])
        self.assertLessEqual(sum(path.stat().st_size for path in self.proxy.request_log_paths() if path.exists()), 50000)

    def test_decreased_limit_trims_closed_archive_with_active_requests(self):
        self.write(Path(str(self.proxy.log_path) + '.1'), 0, 100)
        self.write(self.proxy.log_path, 100, 110)
        self.proxy.settings['maxLogEntries'] = 12
        self.proxy.rotate_logs()
        self.assertEqual(self.entries(), ['/cgi-bin/%d' % number for number in range(98, 110)])

    def test_pending_writer_is_not_modified_until_closed(self):
        self.write(self.proxy.pending_log_path, 0, 300)
        original = self.proxy.pending_log_path.read_bytes()
        with patch.object(self.proxy, 'log_is_open', return_value=True):
            self.proxy.rotate_logs()
        self.assertEqual(self.proxy.pending_log_path.read_bytes(), original)
        self.proxy.rotate_logs()
        self.assertFalse(self.proxy.pending_log_path.exists())
        self.assertEqual(self.entries(), ['/cgi-bin/%d' % number for number in range(100, 300)])

    def test_clear_removes_active_pending_and_archived_records(self):
        for path in self.proxy.request_log_paths():
            self.write(path, 0, 5)
        self.proxy.clear_logs()
        self.assertEqual(self.proxy.logs()['stats']['requests'], 0)
        self.proxy.rotate_logs()
        self.assertEqual(self.entries(), [])

    def test_size_limit_remains_even_with_large_entry_limit(self):
        self.proxy.settings['maxLogEntries'] = 100000
        line = record(0).encode() + b' ' * 8192 + b'\n'
        Path(str(self.proxy.log_path) + '.1').write_bytes(line * 2000)
        self.proxy.rotate_logs()
        self.assertLessEqual(Path(str(self.proxy.log_path) + '.1').stat().st_size, 15 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
