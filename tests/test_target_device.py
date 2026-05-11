import unittest

from src.adb_manager import CommandResult
from src.target_device import AC8267Device, ITargetDevice, UnknownAdbDevice, _normalize_status


class _FakeAdbManager:
    def __init__(self, uuid_success=True, state_success=True, uuid="abc", state="Unauthorized"):
        self._uuid_success = uuid_success
        self._state_success = state_success
        self._uuid = uuid
        self._state = state
        self.activate_calls = []

    def get_device_uuid(self, serial: str):
        return CommandResult(success=self._uuid_success, status_code=0 if self._uuid_success else 1, result_data=self._uuid)

    def get_device_state(self, serial: str):
        return CommandResult(success=self._state_success, status_code=0 if self._state_success else 1, result_data=self._state)

    def activate_device(self, serial: str, signature: str):
        self.activate_calls.append((serial, signature))
        return CommandResult(success=True, status_code=0, result_data="ok")

    def get_authenticator_snapshot(self, serial: str):
        return CommandResult(success=False, status_code=1)


class TestTargetDeviceFactory(unittest.TestCase):
    def test_normalize_status(self):
        self.assertEqual(_normalize_status("authorized"), "Authorized")
        self.assertEqual(_normalize_status("  PIRATED "), "Pirated")
        self.assertEqual(_normalize_status("authorizationfailure"), "AuthorizationFailure")
        self.assertEqual(_normalize_status("checking"), "Unknown")

    def test_create_simulation(self):
        sim = ITargetDevice.CreateSimulation(status="unauthorized", serial_number="SIM-0001")
        self.assertEqual(sim.getType(), "SimulatorDevice")
        self.assertEqual(sim.getSerialNumber(), "SIM-0001")
        self.assertEqual(sim.getStatus(), "Unauthorized")
        self.assertTrue(bool(sim.getUuid()))

    def test_create_simulation_preserves_user_uuid_and_serial(self):
        sim = ITargetDevice.CreateSimulation(
            status="unauthorized",
            serial_number="SIM-USER-0001",
            uuid="UUID-USER-0001",
        )
        self.assertEqual(sim.getSerialNumber(), "SIM-USER-0001")
        self.assertEqual(sim.getUuid(), "UUID-USER-0001")

    def test_simulation_activate_changes_status(self):
        sim = ITargetDevice.CreateSimulation(status="Unauthorized", serial_number="SIM-0002")
        activate_result = sim.activate("dummy")
        self.assertTrue(activate_result.success)
        self.assertEqual(sim.getStatus(), "Authorized")

    def test_simulation_can_force_activation_failure(self):
        sim = ITargetDevice.CreateSimulation(
            status="Unauthorized",
            serial_number="SIM-FAIL-0001",
            uuid="UUID-FAIL-0001",
            fail_on_activate=True,
            failure_reason="SIMULATED_FAIL",
        )
        activate_result = sim.activate("dummy")
        self.assertFalse(activate_result.success)
        self.assertEqual(activate_result.error_message, "SIMULATED_FAIL")
        self.assertEqual(sim.getStatus(), "Unauthorized")

    def test_create_adb_device_as_target(self):
        fake_adb = _FakeAdbManager(uuid_success=True, state_success=True, uuid="uuid-1", state="Unauthorized")
        device = ITargetDevice.CreateAdbDevice(serial_number="A1", adb_manager=fake_adb, usb_port="1-1")
        self.assertIsInstance(device, AC8267Device)
        self.assertEqual(device.getUuid(), "uuid-1")
        self.assertEqual(device.getStatus(), "Unauthorized")
        self.assertEqual(device.getConnectedUsbPort(), "1-1")

    def test_create_adb_device_as_unknown(self):
        fake_adb = _FakeAdbManager(uuid_success=False, state_success=False, uuid="", state="")
        device = ITargetDevice.CreateAdbDevice(serial_number="A2", adb_manager=fake_adb)
        self.assertIsInstance(device, UnknownAdbDevice)
        self.assertEqual(device.getStatus(), "Unknown")


if __name__ == "__main__":
    unittest.main()
