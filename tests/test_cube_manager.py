import threading
import time
import unittest

from src.adb_manager import AuthenticatorInfo, CommandResult
from src.cube_manager import CubeManager


class _FakeAdbManager:
    def __init__(self):
        self.snapshot_calls = []
        self._snapshot_success = True
        self._counter = 0

    def get_authenticator_snapshot(self, serial):
        self.snapshot_calls.append(serial)
        if not self._snapshot_success:
            return CommandResult(success=False, status_code=1, error_message="fail")
        self._counter += 1
        return CommandResult(
            success=True,
            status_code=0,
            raw_output=f"counter={self._counter}",
        )

    def parse_snapshot_data(self, raw_output):
        return AuthenticatorInfo(
            serial="",
            expired_date="2099-12-31",
            counter=self._counter,
            authorized_device_num=0,
            device_status=0,
            time_status="Ready",
            raw_data=raw_output,
        )


class TestCubeManager(unittest.TestCase):
    def setUp(self):
        self.adb = _FakeAdbManager()
        self.cm = CubeManager(self.adb, refresh_interval=5)

    def tearDown(self):
        self.cm.stop(join_timeout=1.0)

    def test_add_and_get_cube(self):
        self.cm.start()
        self.cm.add_cube("CUBE-001")
        time.sleep(0.3)
        self.assertTrue(self.cm.has_cube("CUBE-001"))
        cubes = self.cm.get_cubes()
        self.assertIn("CUBE-001", cubes)
        self.cm.stop(join_timeout=1.0)

    def test_has_cube_returns_false_for_unknown(self):
        self.assertFalse(self.cm.has_cube("UNKNOWN"))

    def test_remove_cube(self):
        self.cm.start()
        self.cm.add_cube("CUBE-001")
        time.sleep(0.3)
        self.assertTrue(self.cm.has_cube("CUBE-001"))
        self.cm.remove_cube("CUBE-001")
        self.assertFalse(self.cm.has_cube("CUBE-001"))
        self.cm.stop(join_timeout=1.0)

    def test_get_cube_serials(self):
        self.cm.start()
        self.cm.add_cube("CUBE-A")
        self.cm.add_cube("CUBE-B")
        time.sleep(0.5)
        serials = self.cm.get_cube_serials()
        self.assertIn("CUBE-A", serials)
        self.assertIn("CUBE-B", serials)
        self.cm.stop(join_timeout=1.0)

    def test_refresh_cube(self):
        self.cm.start()
        self.cm.add_cube("CUBE-001")
        time.sleep(0.3)
        self.cm.refresh_cube("CUBE-001")
        time.sleep(0.3)
        self.assertGreater(len(self.adb.snapshot_calls), 0)
        self.cm.stop(join_timeout=1.0)

    def test_refresh_all_cube(self):
        self.cm.start()
        self.cm.add_cube("CUBE-001")
        self.cm.add_cube("CUBE-002")
        time.sleep(0.5)
        call_count_before = len(self.adb.snapshot_calls)
        self.cm.refresh_all_cube()
        time.sleep(0.5)
        self.assertGreater(len(self.adb.snapshot_calls), call_count_before)
        self.cm.stop(join_timeout=1.0)

    def test_callback_on_cube_added(self):
        received = []
        self.cm.add_callback('authenticator_update', lambda data: received.append(data))
        self.cm.start()
        self.cm.add_cube("CUBE-001")
        time.sleep(0.3)
        self.assertGreater(len(received), 0)
        self.assertIn("CUBE-001", received[-1])
        self.cm.stop(join_timeout=1.0)

    def test_callback_on_cube_removed(self):
        received = []
        self.cm.add_callback('authenticator_update', lambda data: received.append(data))
        self.cm.start()
        self.cm.add_cube("CUBE-001")
        time.sleep(0.3)
        received.clear()
        self.cm.remove_cube("CUBE-001")
        self.assertGreater(len(received), 0)
        self.assertNotIn("CUBE-001", received[-1])
        self.cm.stop(join_timeout=1.0)

    def test_stop_cleans_up(self):
        self.cm.start()
        self.cm.add_cube("CUBE-001")
        time.sleep(0.3)
        self.cm.stop(join_timeout=1.0)
        self.assertFalse(self.cm._running)

    def test_double_start_is_safe(self):
        self.cm.start()
        self.cm.start()
        self.cm.stop(join_timeout=1.0)


if __name__ == "__main__":
    unittest.main()