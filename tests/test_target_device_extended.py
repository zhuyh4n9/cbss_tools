import unittest

from src.adb_manager import CommandResult
from src.target_device import (
    AC8267Device,
    ITargetDevice,
    SimulatorDevice,
    TargetDeviceAbstract,
    UnknownAdbDevice,
    UnknownDevice,
    _normalize_status,
)


class _FakeAdbManager:
    def __init__(self, uuid_success=True, state_success=True, activate_success=True,
                 uuid="uuid-001", state="Unauthorized"):
        self._uuid_success = uuid_success
        self._state_success = state_success
        self._activate_success = activate_success
        self._uuid = uuid
        self._state = state
        self.activate_calls = []
        self.uuid_calls = 0
        self.state_calls = 0

    def get_device_uuid(self, serial):
        self.uuid_calls += 1
        return CommandResult(
            success=self._uuid_success,
            status_code=0 if self._uuid_success else 1,
            result_data=self._uuid,
        )

    def get_device_state(self, serial):
        self.state_calls += 1
        return CommandResult(
            success=self._state_success,
            status_code=0 if self._state_success else 1,
            result_data=self._state,
        )

    def activate_device(self, serial, signature):
        self.activate_calls.append((serial, signature))
        return CommandResult(
            success=self._activate_success,
            status_code=0 if self._activate_success else 1,
            result_data="ok" if self._activate_success else "",
            error_message="" if self._activate_success else "activation failed",
        )


class TestTargetDeviceAbstract(unittest.TestCase):
    def test_mark_dirty_when_unlocked(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        self.assertFalse(device.isDirty())
        device.markDirty()
        self.assertTrue(device.isDirty())

    def test_mark_dirty_when_locked_defers(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        device.lock()
        device.markDirty()
        self.assertFalse(device.isDirty())

    def test_unlock_applies_pending_dirty(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        device.lock()
        device.markDirty()
        self.assertFalse(device.isDirty())
        device.unlock()
        self.assertTrue(device.isDirty())

    def test_lock_returns_false_when_already_locked(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        self.assertTrue(device.lock())
        self.assertFalse(device.lock())

    def test_is_locked(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        self.assertFalse(device.isLocked())
        device.lock()
        self.assertTrue(device.isLocked())
        device.unlock()
        self.assertFalse(device.isLocked())

    def test_mark_dirty_with_parser_kick_callback(self):
        kicked = []
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        device.markDirty(lambda: kicked.append("kicked"))
        self.assertTrue(device.isDirty())
        self.assertEqual(kicked, ["kicked"])

    def test_mark_dirty_locked_no_kick(self):
        kicked = []
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        device.lock()
        device.markDirty(lambda: kicked.append("kicked"))
        self.assertEqual(kicked, [])

    def test_unlock_with_parser_kick(self):
        kicked = []
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        device.lock()
        device.markDirty()
        device.unlock(lambda: kicked.append("kicked"))
        self.assertEqual(kicked, ["kicked"])

    def test_clone_creates_independent_copy(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            status="Unauthorized",
        )
        cloned = device.clone()
        self.assertEqual(cloned.getSerialNumber(), "SIM-001")
        cloned.setStatus("Authorized")
        self.assertEqual(device.getStatus(), "Unauthorized")

    def test_to_device_info_target_device(self):
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=_FakeAdbManager(),
            uuid="uuid-001",
            status="Unauthorized",
            usb_port="1-1",
        )
        info = device.to_device_info()
        self.assertEqual(info.serial, "DEV-001")
        self.assertEqual(info.device_type, "target_device")
        self.assertEqual(info.uuid, "uuid-001")

    def test_to_device_info_unknown_device(self):
        device = UnknownAdbDevice(
            serial_number="DEV-001",
            adb_manager=_FakeAdbManager(),
            status="Unknown",
        )
        info = device.to_device_info()
        self.assertEqual(info.device_type, "unknown")


class TestAC8267Device(unittest.TestCase):
    def test_activate_success_flow(self):
        adb = _FakeAdbManager()
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=adb,
            uuid="uuid-001",
            status="Unauthorized",
        )
        result = device.activate("signature-001")
        self.assertTrue(result.success)
        self.assertTrue(device.isDirty())
        self.assertFalse(device.isLocked())
        self.assertEqual(len(adb.activate_calls), 1)

    def test_activate_failure_marks_authorization_failure(self):
        adb = _FakeAdbManager(activate_success=False)
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=adb,
            uuid="uuid-001",
            status="Unauthorized",
        )
        result = device.activate("signature-001")
        self.assertFalse(result.success)
        self.assertEqual(device.getStatus(), "AuthorizationFailure")
        self.assertFalse(device.isLocked())

    def test_activate_when_dirty_returns_error(self):
        adb = _FakeAdbManager()
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=adb,
            uuid="uuid-001",
            status="Unauthorized",
        )
        device.markDirty()
        result = device.activate("signature-001")
        self.assertFalse(result.success)
        self.assertIn("不可信", result.error_message)

    def test_activate_when_authorization_failure_returns_error(self):
        adb = _FakeAdbManager()
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=adb,
            uuid="uuid-001",
            status="AuthorizationFailure",
        )
        result = device.activate("signature-001")
        self.assertFalse(result.success)
        self.assertIn("AuthorizationFailure", result.error_message)

    def test_activate_when_locked_returns_error(self):
        adb = _FakeAdbManager()
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=adb,
            uuid="uuid-001",
            status="Unauthorized",
        )
        device.lock()
        result = device.activate("signature-001")
        self.assertFalse(result.success)
        self.assertIn("锁定", result.error_message)

    def test_refresh_device_meta(self):
        adb = _FakeAdbManager(uuid="new-uuid", state="Authorized")
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=adb,
            uuid="old-uuid",
            status="Unauthorized",
        )
        device.markDirty()
        device.refreshDeviceMeta()
        self.assertFalse(device.isDirty())
        self.assertEqual(device.getUuid(), "new-uuid")
        self.assertEqual(device.getStatus(), "Authorized")

    def test_refresh_device_meta_skips_authorization_failure(self):
        adb = _FakeAdbManager(uuid="new-uuid", state="Unauthorized")
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=adb,
            uuid="old-uuid",
            status="AuthorizationFailure",
        )
        device.markDirty()
        device.refreshDeviceMeta()
        self.assertFalse(device.isDirty())
        self.assertEqual(device.getUuid(), "old-uuid")
        self.assertEqual(device.getStatus(), "AuthorizationFailure")

    def test_get_status_direct(self):
        adb = _FakeAdbManager(state="Authorized")
        device = AC8267Device(
            serial_number="DEV-001",
            adb_manager=adb,
            uuid="uuid-001",
            status="Unauthorized",
        )
        status = device.getStatusDirect()
        self.assertEqual(status, "Authorized")


class TestSimulatorDevice(unittest.TestCase):
    def test_activate_success(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            uuid="sim-uuid",
            status="Unauthorized",
        )
        result = device.activate("signature")
        self.assertTrue(result.success)
        self.assertEqual(device.getStatus(), "Authorized")

    def test_activate_failure_simulation(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            uuid="sim-uuid",
            status="Unauthorized",
            simulate_activate_failure=True,
        )
        result = device.activate("signature")
        self.assertFalse(result.success)
        self.assertEqual(device.getStatus(), "AuthorizationFailure")

    def test_activate_when_not_unauthorized(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            uuid="sim-uuid",
            status="Authorized",
        )
        result = device.activate("signature")
        self.assertFalse(result.success)

    def test_activate_when_dirty(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            uuid="sim-uuid",
            status="Unauthorized",
        )
        device.markDirty()
        result = device.activate("signature")
        self.assertFalse(result.success)

    def test_refresh_device_meta_clears_dirty(self):
        device = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            uuid="sim-uuid",
            status="Unauthorized",
        )
        device.markDirty()
        device.refreshDeviceMeta()
        self.assertFalse(device.isDirty())


class TestUnknownAdbDevice(unittest.TestCase):
    def test_activate_returns_error(self):
        device = UnknownAdbDevice(
            serial_number="DEV-001",
            adb_manager=_FakeAdbManager(),
            status="Unknown",
        )
        result = device.activate("signature")
        self.assertFalse(result.success)

    def test_refresh_device_meta_clears_dirty(self):
        device = UnknownAdbDevice(
            serial_number="DEV-001",
            adb_manager=_FakeAdbManager(),
            status="Unknown",
        )
        device.markDirty()
        device.refreshDeviceMeta()
        self.assertFalse(device.isDirty())


class TestUnknownDevice(unittest.TestCase):
    def test_get_uuid_returns_placeholder(self):
        device = UnknownDevice(
            detection_method="Unknown",
            serial_number="DEV-001",
        )
        self.assertEqual(device.getUuid(), "UnknownDevice")

    def test_activate_returns_error(self):
        device = UnknownDevice(
            detection_method="Unknown",
            serial_number="DEV-001",
        )
        result = device.activate("signature")
        self.assertFalse(result.success)


class TestNormalizeStatus(unittest.TestCase):
    def test_normalize_known_statuses(self):
        self.assertEqual(_normalize_status("authorized"), "Authorized")
        self.assertEqual(_normalize_status("unauthorized"), "Unauthorized")
        self.assertEqual(_normalize_status("pirated"), "Pirated")
        self.assertEqual(_normalize_status("unknown"), "Unknown")
        self.assertEqual(_normalize_status("authorizationfailure"), "AuthorizationFailure")

    def test_normalize_unknown_status(self):
        self.assertEqual(_normalize_status("checking"), "Unknown")
        self.assertEqual(_normalize_status(""), "Unknown")

    def test_normalize_with_whitespace(self):
        self.assertEqual(_normalize_status("  Authorized  "), "Authorized")


class TestITargetDeviceFactory(unittest.TestCase):
    def test_create_simulation_default_serial(self):
        sim = ITargetDevice.CreateSimulation(status="Unauthorized")
        self.assertTrue(sim.getSerialNumber().startswith("SIM-"))
        self.assertEqual(sim.getStatus(), "Unauthorized")

    def test_create_simulation_with_failure_flag(self):
        sim = ITargetDevice.CreateSimulation(
            status="Unauthorized",
            serial_number="SIM-FAIL",
            simulate_activate_failure=True,
        )
        self.assertTrue(sim.simulate_activate_failure)

    def test_create_adb_device_unknown(self):
        adb = _FakeAdbManager(uuid_success=False, state_success=False)
        device = ITargetDevice.CreateAdbDevice("DEV-001", adb)
        self.assertIsInstance(device, UnknownAdbDevice)


if __name__ == "__main__":
    unittest.main()