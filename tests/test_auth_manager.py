import unittest
import tempfile
import json
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from src.adb_manager import CommandResult, DeviceInfo, AuthenticatorInfo
from src.auth_manager import AuthenticationManager
from src.build_options import SIMULATED_DEVICE_STATUS_OPTIONS
from src.target_device import ITargetDevice


class _FakeConfig:
    def __init__(self, auto_activation_enabled: bool = False):
        self._auto_activation_enabled = bool(auto_activation_enabled)

    def getboolean(self, section, key, default=False):
        if section == "General" and key == "auto_activation_enabled":
            return self._auto_activation_enabled
        return False


class _FakeDeviceParser:
    def add_callback(self, event_type, callback):
        pass


class _FakeDeviceMonitor:
    def __init__(self, events=None, auto_activation_enabled: bool = False):
        self.config = _FakeConfig(auto_activation_enabled=auto_activation_enabled)
        self.device_parser = _FakeDeviceParser()
        self.events = events if events is not None else []
        self.authenticators = {"CUBE-001": AuthenticatorInfo(serial="CUBE-001", time_status="Ready")}
        self.refresh_all_cube_calls = 0
        self.refresh_device_calls = []
        self.refresh_all_device_calls = 0
        self.device_sources = []
        self._devices = {}
        self._simulated_counter = 0
        self._simulated_objects = {}
        self._callbacks = {"device_update": []}

    def refresh_all_cube(self):
        self.refresh_all_cube_calls += 1
        self.events.append("refresh_all_cube")

    def refresh_device(self, serial: str):
        self.refresh_device_calls.append(serial)

    def refresh_all_device(self):
        self.refresh_all_device_calls += 1

    def get_authenticator_by_serial(self, serial: str):
        return self.authenticators.get(serial)

    def register_device_source(self, source):
        self.device_sources.append(source)

    def add_callback(self, event_type, callback):
        self._callbacks.setdefault(event_type, []).append(callback)

    def emit_device_update(self, devices):
        for callback in self._callbacks.get("device_update", []):
            callback(devices)

    def add_simulated_device(self, status: str, serial_id: str = "", uuid: str = "", fail_on_activate: bool = False):
        serial = str(serial_id or "").strip()
        if not serial:
            self._simulated_counter += 1
            serial = f"SIM-{self._simulated_counter:04d}"
        status_input = (status or "").strip().lower()
        status_map = {item.lower(): item for item in SIMULATED_DEVICE_STATUS_OPTIONS}
        normalized_status = status_map.get(status_input, "Unauthorized")
        simulated = ITargetDevice.CreateSimulation(
            status=normalized_status,
            serial_number=serial,
            uuid=uuid or None,
            fail_on_activate=fail_on_activate,
        )
        self._simulated_objects[serial] = simulated
        self._devices[serial] = simulated.to_device_info()
        return simulated.to_device_info()

    def get_simulated_devices(self):
        return [d.to_device_info() for d in self._simulated_objects.values()]

    def is_simulated_device(self, serial: str):
        return str(serial or "") in self._simulated_objects

    def get_simulated_device(self, serial: str):
        return self._simulated_objects.get(str(serial or ""))

    def get_target_device(self, serial: str):
        return self._simulated_objects.get(str(serial or ""))

    def get_device_by_serial(self, serial: str):
        return self._devices.get(serial)

    def get_ready_devices(self):
        return list(self._devices.values())


class _FailingRefreshDeviceMonitor(_FakeDeviceMonitor):
    def refresh_all_cube(self):
        super().refresh_all_cube()
        raise RuntimeError("refresh failed")


class _NoSimulatorAccessorMonitor(_FakeDeviceMonitor):
    def get_simulated_device(self, serial: str):
        raise AssertionError("auth_manager should not access get_simulated_device")


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


class _NoCubeAuthenticationManager(AuthenticationManager):
    TEST_SERIAL = "DEV-NO-CUBE-001"

    def _is_device_still_unauthorized(self, serial: str) -> bool:
        return serial == self.TEST_SERIAL

    def _pick_authenticator(self):
        return None


class _StubCube:
    def __init__(self, serial: str):
        self._serial = serial

    def get_serial(self):
        return self._serial

    def to_authenticator_info(self):
        return AuthenticatorInfo(serial=self._serial, time_status="Ready")


def _write_valid_private_key(path: str):
    key = ec.generate_private_key(ec.SECP256R1())
    with open(path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )


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

    def test_pick_authenticator_prefers_ready_time_status(self):
        fake_monitor = _FakeDeviceMonitor()
        fake_monitor.authenticators = {
            "CUBE-A": AuthenticatorInfo(serial="CUBE-A", time_status="NotReady"),
            "CUBE-B": AuthenticatorInfo(serial="CUBE-B", time_status="Ready"),
            "CUBE-C": AuthenticatorInfo(serial="CUBE-C", time_status=" pending "),
        }
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)

        picked = manager._pick_authenticator()

        self.assertEqual(picked, "CUBE-B")

    def test_pick_authenticator_falls_back_to_available_when_no_ready(self):
        fake_monitor = _FakeDeviceMonitor()
        fake_monitor.authenticators = {
            "CUBE-A": AuthenticatorInfo(serial="CUBE-A", time_status="NotReady"),
            "CUBE-C": AuthenticatorInfo(serial="CUBE-C", time_status=" pending "),
        }
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)

        picked = manager._pick_authenticator()

        self.assertEqual(picked, "CUBE-A")

    def test_unauthorized_enqueue_clears_auto_completed_flag(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)
        manager._auto_activation_enabled = True

        serial = "DEV-QUEUE-001"
        manager._auto_activation_completed_serials.add(serial)
        manager._on_unauthorized_ready(DeviceInfo(serial=serial, status="Unauthorized", uuid="UUID-001"))

        self.assertTrue(manager.is_device_queued_for_auto_activation(serial))
        self.assertFalse(manager.is_device_auto_activation_completed(serial))

    def test_waiting_for_cube_keeps_device_marked_as_queued(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = _NoCubeAuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)
        manager._auto_activation_enabled = True
        manager._worker_running = True
        manager._stop_event.clear()

        serial = manager.TEST_SERIAL
        manager._queued_serials.add(serial)
        manager._activate_queue.put(serial)
        manager._activate_queue.put(None)

        def _fake_sleep(_seconds):
            self.assertTrue(manager.is_device_queued_for_auto_activation(serial))

        with patch("src.auth_manager.time.sleep", side_effect=_fake_sleep):
            manager._activate_worker_loop()

        self.assertTrue(manager.is_device_queued_for_auto_activation(serial))

    def test_device_update_enqueues_unauthorized_device_for_auto_activation(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)
        manager._auto_activation_enabled = True

        device = DeviceInfo(serial="DEV-QUEUE-BY-UPDATE-001", status="Unauthorized", uuid="UUID-READY-001")
        manager._on_device_update([device])

        self.assertTrue(manager.is_device_queued_for_auto_activation(device.serial))

    def test_resolve_target_device_does_not_use_simulator_accessor(self):
        fake_monitor = _NoSimulatorAccessorMonitor()
        simulated = fake_monitor.add_simulated_device("Unauthorized", serial_id="SIM-NO-ACCESS-001")
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)

        resolved = manager._resolve_target_device(simulated.serial)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.to_device_info().serial, simulated.serial)

    def test_simulated_device_source_and_auth_flow(self):
        events = []
        fake_monitor = _FakeDeviceMonitor(events=events)
        fake_adb_manager = _FakeAdbManager(events=events)

        with patch("src.auth_manager.ENABLE_SIMULATED_DEVICE", True):
            manager = AuthenticationManager(adb_manager=fake_adb_manager, device_monitor=fake_monitor)
            simulated = fake_monitor.add_simulated_device("Unauthorized")

            self.assertTrue(fake_monitor.is_simulated_device(simulated.serial))
            self.assertEqual(len(fake_monitor.get_simulated_devices()), 1)

            result = manager._perform_authentication(simulated.serial, "CUBE-001")

            self.assertTrue(result["success"])
            self.assertIn("authenticator_sign", events)
            self.assertNotIn("get_device_uuid", events)
            self.assertNotIn("verify_device_state", events)
            self.assertEqual(fake_monitor.get_simulated_devices()[0].status, "Authorized")

    def test_failed_activation_is_blocked_until_unplug_and_written_to_critical_log(self):
        events = []
        fake_monitor = _FakeDeviceMonitor(events=events)
        fake_adb_manager = _FakeAdbManager(events=events)
        manager = AuthenticationManager(adb_manager=fake_adb_manager, device_monitor=fake_monitor)

        with tempfile.TemporaryDirectory() as tmpdir, patch("src.auth_manager.ENABLE_SIMULATED_DEVICE", True):
            manager._CRITICAL_BUG_LOG_PATH = f"{tmpdir}/critical_bug.log"
            simulated = fake_monitor.add_simulated_device(
                status="Unauthorized",
                serial_id="SIM-FAIL-LOCK-001",
                uuid="UUID-FAIL-LOCK-001",
                fail_on_activate=True,
            )

            first = manager._perform_authentication(simulated.serial, "CUBE-001")
            second = manager._perform_authentication(simulated.serial, "CUBE-001")

            self.assertFalse(first["success"])
            self.assertFalse(second["success"])
            self.assertEqual(fake_monitor.get_simulated_devices()[0].status, "AuthorizationFailure")
            self.assertIn("已锁定", second["message"])
            self.assertEqual(events.count("authenticator_sign"), 1)
            self.assertTrue(manager.is_device_activation_blocked(simulated.serial))

            with open(manager._CRITICAL_BUG_LOG_PATH, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            self.assertGreaterEqual(len(lines), 1)
            payload = json.loads(lines[-1])
            self.assertEqual(payload["serial"], simulated.serial)
            self.assertEqual(payload["uuid"], "UUID-FAIL-LOCK-001")
            self.assertTrue(bool(payload["signature"]))

            fake_monitor.emit_device_update([])
            self.assertFalse(manager.is_device_activation_blocked(simulated.serial))

            fail_sim = fake_monitor.get_simulated_device(simulated.serial)
            fail_sim.fail_on_activate = False
            fail_sim.setStatus("Unauthorized")
            third = manager._perform_authentication(simulated.serial, "CUBE-001")
            self.assertTrue(third["success"])

    def test_create_simulated_cube_uses_icube_factory(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/p256.pem"
            persist_path = f"{tmpdir}/cube.json"
            _write_valid_private_key(key_path)

            with patch("src.auth_manager.ENABLE_SIMULATED_DEVICE", True), \
                    patch("src.auth_manager.ICube.CreateSimulation", return_value=_StubCube("CUSTOM-001")) as create_mock:
                serial = manager.create_simulated_cube(
                    expired_date="2099-12-31",
                    counter=3,
                    private_key_path=key_path,
                    cube_id="CUBE-A",
                    oem_id="OEM-A",
                    persist_path=persist_path,
                    serial_id="CUSTOM-001",
                )

        self.assertEqual(serial, "CUSTOM-001")
        self.assertTrue(manager.is_simulated_cube("CUSTOM-001"))
        create_mock.assert_called_once()

    def test_load_simulated_cube_uses_icube_factory(self):
        fake_monitor = _FakeDeviceMonitor()
        manager = AuthenticationManager(adb_manager=_FakeAdbManager(), device_monitor=fake_monitor)

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = f"{tmpdir}/p256.pem"
            persist_path = f"{tmpdir}/cube.json"
            _write_valid_private_key(key_path)
            with open(persist_path, "w", encoding="utf-8") as f:
                f.write("{}")

            with patch("src.auth_manager.ENABLE_SIMULATED_DEVICE", True), \
                    patch("src.auth_manager.ICube.LoadSimulation", return_value=_StubCube("CUSTOM-LOAD-001")) as load_mock:
                serial = manager.load_simulated_cube(
                    persist_path=persist_path,
                    private_key_path=key_path,
                    serial_id="CUSTOM-LOAD-001",
                )

        self.assertEqual(serial, "CUSTOM-LOAD-001")
        self.assertTrue(manager.is_simulated_cube("CUSTOM-LOAD-001"))
        load_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
