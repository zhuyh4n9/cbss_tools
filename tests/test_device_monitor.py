import unittest
from unittest.mock import patch

from src.adb_manager import DeviceInfo
from src.device_monitor import DeviceMonitor


class _FakeConfig:
    def getint(self, section, key, default=0):
        return default


class _FakeParser:
    def __init__(self, _adb_manager):
        self.sync_calls = []

    def add_callback(self, event_type, callback):
        pass

    def sync_connected_devices(self, devices):
        self.sync_calls.append(devices)

    def refresh_all_cube(self):
        pass

    def get_authenticator_serials(self):
        return []


class _FakeSource:
    def __init__(self, devices):
        self.devices = devices

    def poll_devices(self):
        return list(self.devices)


class TestDeviceMonitorUpdateBehavior(unittest.TestCase):
    @patch("src.device_monitor.DeviceParser", _FakeParser)
    def test_update_device_info_only_syncs_when_connected_state_changes(self):
        monitor = DeviceMonitor(adb_manager=object(), config_manager=_FakeConfig())
        source = _FakeSource([
            DeviceInfo(serial="DEV-001", status="device", usb_port="1-1", detection_method="Adb"),
        ])
        monitor._device_sources = {"Adb": source}

        monitor._update_device_info()
        self.assertEqual(len(monitor.device_parser.sync_calls), 1)

        monitor._update_device_info()
        self.assertEqual(len(monitor.device_parser.sync_calls), 1)

        source.devices = [
            DeviceInfo(serial="DEV-001", status="offline", usb_port="1-1", detection_method="Adb"),
        ]
        monitor._update_device_info()
        self.assertEqual(len(monitor.device_parser.sync_calls), 2)

    @patch("src.device_monitor.ENABLE_SIMULATED_DEVICE", True)
    @patch("src.device_monitor.DeviceParser", _FakeParser)
    def test_add_simulated_device_managed_by_monitor(self):
        monitor = DeviceMonitor(adb_manager=object(), config_manager=_FakeConfig())
        simulated = DeviceMonitor.create_simulated_device(monitor, "Unauthorized")

        self.assertTrue(monitor.is_simulated_device(simulated.serial))
        self.assertEqual(simulated.detection_method, "Simulation")
        self.assertEqual(simulated.status, "Unauthorized")

    @patch("src.device_monitor.ENABLE_SIMULATED_DEVICE", True)
    @patch("src.device_monitor.DeviceParser", _FakeParser)
    def test_remove_simulated_device(self):
        monitor = DeviceMonitor(adb_manager=object(), config_manager=_FakeConfig())
        simulated = DeviceMonitor.create_simulated_device(monitor, "Unauthorized")

        removed = monitor.remove_simulated_device(simulated.serial)

        self.assertTrue(removed)
        self.assertFalse(monitor.is_simulated_device(simulated.serial))


if __name__ == "__main__":
    unittest.main()
