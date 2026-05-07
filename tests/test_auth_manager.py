import unittest

from src.auth_manager import AuthenticationManager


class _FakeConfig:
    def getboolean(self, section, key, default=False):
        return False


class _FakeDeviceParser:
    def add_callback(self, event_type, callback):
        self._callback = (event_type, callback)


class _FakeDeviceMonitor:
    def __init__(self):
        self.config = _FakeConfig()
        self.device_parser = _FakeDeviceParser()
        self.refresh_all_cube_calls = 0
        self.refresh_device_calls = []
        self.refresh_all_device_calls = 0

    def refresh_all_cube(self):
        self.refresh_all_cube_calls += 1

    def refresh_device(self, serial: str):
        self.refresh_device_calls.append(serial)

    def refresh_all_device(self):
        self.refresh_all_device_calls += 1


class TestAuthenticationManagerAutoRefresh(unittest.TestCase):
    def test_auto_activation_refreshes_only_current_device(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = AuthenticationManager(adb_manager=object(), device_monitor=fake_monitor)

        manager._worker_running = True
        manager._stop_event.clear()
        manager._activate_queue.put("DEV-001")
        manager._activate_queue.put(None)

        manager._is_device_still_unauthorized = lambda serial: True
        manager._pick_authenticator = lambda: "CUBE-001"
        manager._run_authentication = lambda serial, auth_serial: {"success": True}

        manager._activate_worker_loop()

        self.assertEqual(fake_monitor.refresh_all_cube_calls, 1)
        self.assertEqual(fake_monitor.refresh_device_calls, ["DEV-001"])
        self.assertEqual(fake_monitor.refresh_all_device_calls, 0)


if __name__ == "__main__":
    unittest.main()
