import unittest

from src.auth_manager import AuthenticationManager


class _FakeConfig:
    def getboolean(self, section, key, default=False):
        return False


class _FakeDeviceParser:
    def add_callback(self, event_type, callback):
        self._unused_callback = (event_type, callback)


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


class _FakeAdbManager:
    pass


class _TestableAuthenticationManager(AuthenticationManager):
    def __init__(self, adb_manager, device_monitor):
        super().__init__(adb_manager, device_monitor)
        self._unauthorized_serials = {"DEV-001"}

    def _is_device_still_unauthorized(self, serial: str) -> bool:
        return str(serial) in self._unauthorized_serials

    def _pick_authenticator(self):
        return "CUBE-001"

    def _run_authentication(self, device_serial: str, authenticator_serial: str, progress_callback=None) -> dict:
        self._unauthorized_serials.discard(str(device_serial))
        return {"success": True}


class TestAuthenticationManagerAutoRefresh(unittest.TestCase):
    def test_auto_activation_refreshes_only_current_device(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = _TestableAuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)

        manager._worker_running = True
        manager._stop_event.clear()
        manager._activate_queue.put("DEV-001")
        manager._activate_queue.put(None)

        manager._activate_worker_loop()

        self.assertEqual(fake_monitor.refresh_all_cube_calls, 1)
        self.assertEqual(fake_monitor.refresh_device_calls, ["DEV-001"])
        self.assertEqual(fake_monitor.refresh_all_device_calls, 0)


if __name__ == "__main__":
    unittest.main()
