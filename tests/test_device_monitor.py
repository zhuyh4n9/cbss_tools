import unittest

from src.adb_manager import DeviceInfo
from src.device_monitor import DeviceMonitor


class _FakeConfig:
    def getint(self, section, key, default=0):
        return default


class _FakeSource:
    def __init__(self, devices):
        self._devices = list(devices)

    def set_devices(self, devices):
        self._devices = list(devices)

    def start(self):
        return

    def stop(self):
        return

    def poll_devices(self):
        return list(self._devices)


class _FakeDeviceParser:
    def __init__(self):
        self.sync_calls = []

    def add_callback(self, event_type, callback):
        return

    def sync_connected_devices(self, devices):
        self.sync_calls.append([d.serial for d in devices])

    def start(self):
        return

    def stop(self, join_timeout=2.0):
        return

    def refresh_all_cube(self):
        return

    def get_authenticator_serials(self):
        return []


class _FakeAdbManager:
    pass


class TestDeviceMonitorChangeDetection(unittest.TestCase):
    def _make_monitor(self, source):
        monitor = DeviceMonitor(adb_manager=_FakeAdbManager(), config_manager=_FakeConfig())
        monitor._device_sources = {"Fake": source}
        monitor.device_parser = _FakeDeviceParser()
        return monitor

    def test_sync_connected_devices_only_runs_when_state_changes(self):
        source = _FakeSource([
            DeviceInfo(serial="DEV-001", status="device", usb_port="1-1", detection_method="Adb")
        ])
        monitor = self._make_monitor(source)

        monitor._update_device_info()
        self.assertEqual(monitor.device_parser.sync_calls, [["DEV-001"]])

        monitor._update_device_info()
        self.assertEqual(len(monitor.device_parser.sync_calls), 1)

        source.set_devices([
            DeviceInfo(serial="DEV-001", status="unauthorized", usb_port="1-1", detection_method="Adb")
        ])
        monitor._update_device_info()
        self.assertEqual(len(monitor.device_parser.sync_calls), 2)


if __name__ == "__main__":
    unittest.main()
