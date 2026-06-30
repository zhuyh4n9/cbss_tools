import unittest

from src.adb_manager import DeviceInfo
from src.device_source import (
    AdbDeviceDetector,
    DeviceChange,
    SimulatorDeviceDetector,
)


class _FakeAdbManager:
    def __init__(self, devices=None):
        self._devices = devices or []

    def get_connected_devices(self):
        result = []
        for d in self._devices:
            result.append(DeviceInfo(
                serial=d.serial,
                status=d.status,
                device_type=d.device_type,
                uuid=d.uuid,
                usb_port=d.usb_port,
                detection_method="Adb",
                is_simulation=d.is_simulation,
            ))
        return result


class TestAdbDeviceDetector(unittest.TestCase):
    def test_poll_devices_returns_adb_devices(self):
        fake_adb = _FakeAdbManager([
            DeviceInfo(serial="DEV-001", status="device", usb_port="1-1"),
            DeviceInfo(serial="DEV-002", status="device", usb_port="1-2"),
        ])
        detector = AdbDeviceDetector(fake_adb)
        devices = detector.poll_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].serial, "DEV-001")
        self.assertEqual(devices[0].detection_method, "Adb")

    def test_poll_changes_first_call_returns_all_as_added(self):
        fake_adb = _FakeAdbManager([
            DeviceInfo(serial="DEV-001", status="device"),
        ])
        detector = AdbDeviceDetector(fake_adb)
        change = detector.poll_changes()
        self.assertEqual(len(change.added), 1)
        self.assertEqual(change.added[0].serial, "DEV-001")
        self.assertEqual(len(change.removed), 0)

    def test_poll_changes_detects_added(self):
        fake_adb = _FakeAdbManager([
            DeviceInfo(serial="DEV-001", status="device"),
        ])
        detector = AdbDeviceDetector(fake_adb)
        detector.poll_changes()

        fake_adb._devices.append(DeviceInfo(serial="DEV-002", status="device"))
        change = detector.poll_changes()
        self.assertEqual(len(change.added), 1)
        self.assertEqual(change.added[0].serial, "DEV-002")
        self.assertEqual(len(change.removed), 0)

    def test_poll_changes_detects_removed(self):
        fake_adb = _FakeAdbManager([
            DeviceInfo(serial="DEV-001", status="device"),
            DeviceInfo(serial="DEV-002", status="device"),
        ])
        detector = AdbDeviceDetector(fake_adb)
        detector.poll_changes()

        fake_adb._devices = [DeviceInfo(serial="DEV-001", status="device")]
        change = detector.poll_changes()
        self.assertEqual(len(change.added), 0)
        self.assertEqual(len(change.removed), 1)
        self.assertEqual(change.removed[0], "DEV-002")

    def test_poll_changes_detects_both_added_and_removed(self):
        fake_adb = _FakeAdbManager([
            DeviceInfo(serial="DEV-001", status="device"),
            DeviceInfo(serial="DEV-002", status="device"),
        ])
        detector = AdbDeviceDetector(fake_adb)
        detector.poll_changes()

        fake_adb._devices = [
            DeviceInfo(serial="DEV-001", status="device"),
            DeviceInfo(serial="DEV-003", status="device"),
        ]
        change = detector.poll_changes()
        self.assertEqual(len(change.added), 1)
        self.assertEqual(change.added[0].serial, "DEV-003")
        self.assertEqual(len(change.removed), 1)
        self.assertEqual(change.removed[0], "DEV-002")

    def test_poll_changes_no_change(self):
        fake_adb = _FakeAdbManager([
            DeviceInfo(serial="DEV-001", status="device"),
        ])
        detector = AdbDeviceDetector(fake_adb)
        detector.poll_changes()
        change = detector.poll_changes()
        self.assertEqual(len(change.added), 0)
        self.assertEqual(len(change.removed), 0)

    def test_get_name(self):
        detector = AdbDeviceDetector(_FakeAdbManager())
        self.assertEqual(detector.get_name(), "Adb")


class TestSimulatorDeviceDetector(unittest.TestCase):
    def setUp(self):
        self.detector = SimulatorDeviceDetector()

    def test_add_device_creates_simulator(self):
        device_info = self.detector.add_device("Unauthorized")
        self.assertTrue(device_info.serial.startswith("SIM-"))
        self.assertEqual(device_info.status, "Unauthorized")
        self.assertTrue(device_info.uuid)

    def test_add_device_with_custom_serial(self):
        device_info = self.detector.add_device("Authorized", serial_number="MY-SIM-001")
        self.assertEqual(device_info.serial, "MY-SIM-001")
        self.assertEqual(device_info.status, "Authorized")

    def test_poll_changes_returns_pending_and_clears(self):
        self.detector.add_device("Unauthorized")
        change = self.detector.poll_changes()
        self.assertEqual(len(change.added), 1)
        self.assertEqual(len(change.removed), 0)

        change2 = self.detector.poll_changes()
        self.assertEqual(len(change2.added), 0)
        self.assertEqual(len(change2.removed), 0)

    def test_remove_device(self):
        device_info = self.detector.add_device("Unauthorized", serial_number="SIM-RM-001")
        self.detector.poll_changes()

        self.detector.remove_device("SIM-RM-001")
        change = self.detector.poll_changes()
        self.assertEqual(len(change.added), 0)
        self.assertEqual(len(change.removed), 1)
        self.assertEqual(change.removed[0], "SIM-RM-001")

    def test_get_device(self):
        self.detector.add_device("Unauthorized", serial_number="SIM-GET-001")
        device = self.detector.get_device("SIM-GET-001")
        self.assertIsNotNone(device)
        self.assertEqual(device.getSerialNumber(), "SIM-GET-001")

    def test_get_device_nonexistent(self):
        self.assertIsNone(self.detector.get_device("NONEXISTENT"))

    def test_poll_devices_returns_all(self):
        self.detector.add_device("Unauthorized", serial_number="SIM-A")
        self.detector.add_device("Authorized", serial_number="SIM-B")
        devices = self.detector.poll_devices()
        self.assertEqual(len(devices), 2)

    def test_get_name(self):
        self.assertEqual(self.detector.get_name(), "Simulator")

    def test_add_device_with_simulate_activate_failure(self):
        device_info = self.detector.add_device("Unauthorized", serial_number="SIM-FAIL-001",
                                                simulate_activate_failure=True)
        self.assertEqual(device_info.serial, "SIM-FAIL-001")
        from src.device_source import SimulatorDeviceDetector
        self.assertTrue(SimulatorDeviceDetector._sim_failure_flags.get("SIM-FAIL-001", False))

    def test_device_change_dataclass(self):
        change = DeviceChange(
            added=[DeviceInfo(serial="A", status="device")],
            removed=["B"],
        )
        self.assertEqual(len(change.added), 1)
        self.assertEqual(len(change.removed), 1)


if __name__ == "__main__":
    unittest.main()