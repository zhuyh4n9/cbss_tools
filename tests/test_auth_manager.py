import unittest

from src.adb_manager import CommandResult, DeviceInfo, AuthenticatorInfo
from src.auth_manager import AuthenticationManager


class _FakeConfig:
    def getboolean(self, section, key, default=False):
        return False


class _FakeDeviceParser:
    def add_callback(self, event_type, callback):
        pass


class _FakeSimDetector:
    def get_device(self, serial: str):
        return None


class _FakeDeviceMonitor:
    def __init__(self, events=None):
        self.config = _FakeConfig()
        self.device_parser = _FakeDeviceParser()
        self.events = events if events is not None else []
        self.authenticators = {"CUBE-001": AuthenticatorInfo(serial="CUBE-001", time_status="Ready")}
        self.refresh_all_cube_calls = 0
        self.refresh_device_calls = []
        self.refresh_all_device_calls = 0
        self.sim_detector = _FakeSimDetector()
        self._simulated_cubes = {}
        self.target_devices = []

    def refresh_all_cube(self):
        self.refresh_all_cube_calls += 1
        self.events.append("refresh_all_cube")

    def refresh_device(self, serial: str):
        self.refresh_device_calls.append(serial)

    def refresh_all_device(self):
        self.refresh_all_device_calls += 1

    def get_authenticator_by_serial(self, serial: str):
        return self.authenticators.get(serial)

    def is_simulated_cube(self, serial: str) -> bool:
        return False


class _FailingRefreshDeviceMonitor(_FakeDeviceMonitor):
    def refresh_all_cube(self):
        super().refresh_all_cube()
        raise RuntimeError("refresh failed")


class _FakeAdbManager:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self._activation_done = False

    def get_device_uuid(self, serial: str):
        self.events.append("get_device_uuid")
        return CommandResult(success=True, status_code=0, result_data="UUID-001", raw_output="UUID-001")

    def authenticator_sign(self, authenticator_serial: str, uuid: str):
        self.events.append("authenticator_sign")
        return CommandResult(success=True, status_code=0, result_data="SIGNATURE-001", raw_output="SIGNATURE-001")

    def activate_device(self, serial: str, signature: str):
        self.events.append("activate_device")
        self._activation_done = True
        return CommandResult(success=True, status_code=0, result_data="OK", raw_output="OK")

    def get_device_state(self, serial: str):
        if self._activation_done:
            self.events.append("verify_device_state")
            return CommandResult(success=True, status_code=0, result_data="Authorized", raw_output="Authorized")
        self.events.append("precheck_device_state")
        return CommandResult(success=True, status_code=0, result_data="Unauthorized", raw_output="Unauthorized")


class _TestableAuthenticationManager(AuthenticationManager):
    TEST_SERIAL = "DEV-001"

    def __init__(self, adb_manager, device_monitor):
        super().__init__(adb_manager, device_monitor)
        self._unauthorized_serials = {self.TEST_SERIAL}

    def _is_device_still_unauthorized(self, serial: str) -> bool:
        return serial in self._unauthorized_serials

    def _pick_authenticator(self):
        return "CUBE-001"

    def _run_authentication(self, device_serial: str, authenticator_serial: str, progress_callback=None) -> dict:
        self._unauthorized_serials.discard(device_serial)
        return {"success": True}


class TestAuthenticationManagerAutoRefresh(unittest.TestCase):
    def test_auto_activation_refreshes_only_current_device(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = _TestableAuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)

        manager._worker_running = True
        manager._stop_event.clear()
        manager._activate_queue.put(manager.TEST_SERIAL)
        manager._activate_queue.put(None)

        manager._activate_worker_loop()

        self.assertEqual(fake_monitor.refresh_all_cube_calls, 1)
        self.assertEqual(fake_monitor.refresh_device_calls, [manager.TEST_SERIAL])
        self.assertEqual(fake_monitor.refresh_all_device_calls, 0)

    def test_refresh_cube_after_activation(self):
        events = []
        fake_monitor = _FakeDeviceMonitor(events=events)
        fake_adb_manager = _FakeAdbManager(events=events)
        manager = AuthenticationManager(adb_manager=fake_adb_manager, device_monitor=fake_monitor)

        result = manager._perform_authentication("DEV-001", "CUBE-001")

        self.assertTrue(result["success"])
        self.assertEqual(fake_monitor.refresh_all_cube_calls, 1)
        self.assertIn("activate_device", events)
        self.assertIn("refresh_all_cube", events)
        self.assertIn("verify_device_state", events)
        self.assertEqual(events.count("activate_device"), 1)
        self.assertEqual(events.count("refresh_all_cube"), 1)
        self.assertEqual(events.count("verify_device_state"), 1)
        positions = {
            name: events.index(name)
            for name in ("activate_device", "refresh_all_cube", "verify_device_state")
        }
        self.assertLess(positions["activate_device"], positions["refresh_all_cube"])
        self.assertLess(positions["refresh_all_cube"], positions["verify_device_state"])

    def test_refresh_cube_error_does_not_break_authentication(self):
        fake_monitor = _FailingRefreshDeviceMonitor()
        fake_adb_manager = _FakeAdbManager()
        manager = AuthenticationManager(adb_manager=fake_adb_manager, device_monitor=fake_monitor)

        with self.assertLogs(level="WARNING") as log_output:
            result = manager._perform_authentication("DEV-001", "CUBE-001")

        self.assertTrue(result["success"])
        self.assertEqual(fake_monitor.refresh_all_cube_calls, 1)
        self.assertGreater(len(log_output.output), 0)

    def test_pick_authenticator_requires_ready_time_status(self):
        fake_monitor = _FakeDeviceMonitor()
        fake_monitor.authenticators = {
            "CUBE-A": AuthenticatorInfo(serial="CUBE-A", time_status="NotReady"),
            "CUBE-B": AuthenticatorInfo(serial="CUBE-B", time_status="Ready"),
            "CUBE-C": AuthenticatorInfo(serial="CUBE-C", time_status=" pending "),
        }
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)

        picked = manager._pick_authenticator()

        self.assertEqual(picked, "CUBE-B")

    def test_unauthorized_enqueue_clears_auto_completed_flag(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)
        manager._auto_activation_enabled = True

        serial = "DEV-QUEUE-001"
        manager._auto_activation_completed_serials.add(serial)
        manager._on_unauthorized_ready(DeviceInfo(serial=serial, status="Unauthorized", uuid="UUID-001"))

        self.assertTrue(manager.is_device_queued_for_auto_activation(serial))
        self.assertFalse(manager.is_device_auto_activation_completed(serial))


if __name__ == "__main__":
    unittest.main()
