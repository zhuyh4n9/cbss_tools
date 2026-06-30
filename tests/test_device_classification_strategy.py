import unittest

from src.adb_manager import CommandResult
from src.device_classification_strategy import (
    ClassificationDecision,
    DeviceClassificationStrategy,
)
from src.target_device import (
    AC8267Device,
    SimulatorDevice,
    UnknownAdbDevice,
    UnknownDevice,
)


class _FakeAdbManager:
    def __init__(self, uuid_success=True, state_success=True, snapshot_success=False):
        self._uuid_success = uuid_success
        self._state_success = state_success
        self._snapshot_success = snapshot_success

    def get_device_uuid(self, serial):
        return CommandResult(
            success=self._uuid_success,
            status_code=0 if self._uuid_success else 1,
            result_data="uuid-001" if self._uuid_success else "",
        )

    def get_device_state(self, serial):
        return CommandResult(
            success=self._state_success,
            status_code=0 if self._state_success else 1,
            result_data="Unauthorized" if self._state_success else "",
        )

    def get_authenticator_snapshot(self, serial):
        return CommandResult(
            success=self._snapshot_success,
            status_code=0 if self._snapshot_success else 1,
            result_data="snapshot_data" if self._snapshot_success else "",
        )


class TestDeviceClassificationStrategy(unittest.TestCase):
    def setUp(self):
        self.adb = _FakeAdbManager()
        self.strategy = DeviceClassificationStrategy(self.adb)

    def test_classify_known_cube_returns_none(self):
        base = UnknownAdbDevice(serial_number="DEV-001", adb_manager=self.adb)
        decision = self.strategy.classify_device("DEV-001", base, known_cube=True)
        self.assertIsNone(decision.ready_device)
        self.assertFalse(decision.should_add_cube)
        self.assertFalse(decision.should_mark_unknown)

    def test_classify_adb_device_as_ac8267(self):
        base = UnknownAdbDevice(serial_number="DEV-001", adb_manager=self.adb)
        decision = self.strategy.classify_device("DEV-001", base, known_cube=False)
        self.assertIsInstance(decision.ready_device, AC8267Device)
        self.assertFalse(decision.should_add_cube)

    def test_classify_adb_device_as_cube_when_snapshot_succeeds(self):
        adb = _FakeAdbManager(uuid_success=False, state_success=False, snapshot_success=True)
        strategy = DeviceClassificationStrategy(adb)
        base = UnknownAdbDevice(serial_number="DEV-001", adb_manager=adb)
        decision = strategy.classify_device("DEV-001", base, known_cube=False)
        self.assertIsNone(decision.ready_device)
        self.assertTrue(decision.should_add_cube)

    def test_classify_adb_device_as_unknown_when_all_fail(self):
        adb = _FakeAdbManager(uuid_success=False, state_success=False, snapshot_success=False)
        strategy = DeviceClassificationStrategy(adb)
        base = UnknownAdbDevice(serial_number="DEV-001", adb_manager=adb)
        decision = strategy.classify_device("DEV-001", base, known_cube=False)
        self.assertIsNone(decision.ready_device)
        self.assertFalse(decision.should_add_cube)
        self.assertTrue(decision.should_mark_unknown)

    def test_classify_simulator_device(self):
        base = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            uuid="sim-uuid",
            status="Unauthorized",
            usb_port="SIM",
        )
        decision = self.strategy.classify_device("SIM-001", base, known_cube=False)
        self.assertIsInstance(decision.ready_device, SimulatorDevice)
        self.assertEqual(decision.ready_device.getSerialNumber(), "SIM-001")

    def test_classify_unknown_detection_method(self):
        base = UnknownDevice(
            detection_method="Bluetooth",
            serial_number="BT-001",
            is_simulation=False,
            usb_port="",
        )
        decision = self.strategy.classify_device("BT-001", base, known_cube=False)
        self.assertIsInstance(decision.ready_device, UnknownDevice)

    def test_refresh_await_device_adb(self):
        base = UnknownAdbDevice(serial_number="DEV-001", adb_manager=self.adb)
        refreshed = self.strategy.refresh_await_device("DEV-001", base)
        self.assertIsInstance(refreshed, AC8267Device)

    def test_refresh_await_device_simulator(self):
        base = SimulatorDevice(
            detection_method="Simulation",
            serial_number="SIM-001",
            is_simulation=True,
            uuid="sim-uuid",
            status="Unauthorized",
            usb_port="SIM",
        )
        refreshed = self.strategy.refresh_await_device("SIM-001", base)
        self.assertIsInstance(refreshed, SimulatorDevice)
        self.assertEqual(refreshed.getSerialNumber(), "SIM-001")

    def test_classification_decision_dataclass(self):
        decision = ClassificationDecision(
            ready_device=None,
            should_add_cube=True,
            should_mark_unknown=False,
        )
        self.assertTrue(decision.should_add_cube)
        self.assertFalse(decision.should_mark_unknown)


if __name__ == "__main__":
    unittest.main()