import unittest
from unittest.mock import patch

from src.adb_manager import DeviceInfo
from src.device_monitor import DeviceMonitor


class _FakeConfig:
    def getint(self, section, key, default=0):
        return default

    def getboolean(self, section, key, default=False):
        return default

    def getfloat(self, section, key, default=0.0):
        return default


class _FakeParser:
    def __init__(self, _adb_manager):
        self.sync_calls = []
        self.started = False
        self.stopped = False

    def add_callback(self, event_type, callback):
        pass

    def start(self):
        self.started = True

    def stop(self, join_timeout=2.0):
        self.stopped = True

    def sync_connected_devices(self, devices):
        self.sync_calls.append(devices)

    def refresh_all_cube(self):
        pass

    def get_authenticator_serials(self):
        return []


class _FakeSource:
    def __init__(self, devices):
        self.devices = devices
        self.poll_calls = 0
        self.started = False
        self.stopped = False

    def poll_devices(self):
        self.poll_calls += 1
        return list(self.devices)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


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
    def test_add_simulated_device_uses_user_serial_and_uuid(self):
        monitor = DeviceMonitor(adb_manager=object(), config_manager=_FakeConfig())
        simulated = DeviceMonitor.create_simulated_device(
            monitor,
            "Unauthorized",
            serial_id="SIM-USER-1001",
            uuid="UUID-USER-1001",
            fail_on_activate=True,
        )

        self.assertEqual(simulated.serial, "SIM-USER-1001")
        self.assertEqual(simulated.uuid, "UUID-USER-1001")
        target = monitor.get_simulated_device("SIM-USER-1001")
        self.assertTrue(target.fail_on_activate)

    @patch("src.device_monitor.ENABLE_SIMULATED_DEVICE", True)
    @patch("src.device_monitor.DeviceParser", _FakeParser)
    def test_remove_simulated_device(self):
        monitor = DeviceMonitor(adb_manager=object(), config_manager=_FakeConfig())
        simulated = DeviceMonitor.create_simulated_device(monitor, "Unauthorized")

        removed = monitor.remove_simulated_device(simulated.serial)

        self.assertTrue(removed)
        self.assertFalse(monitor.is_simulated_device(simulated.serial))

    @patch("src.device_monitor.DeviceParser", _FakeParser)
    def test_start_monitoring_without_periodic_polling_skips_background_thread(self):
        config = _FakeConfig()
        monitor = DeviceMonitor(adb_manager=object(), config_manager=config)
        source = _FakeSource([
            DeviceInfo(serial="DEV-001", status="device", usb_port="1-1", detection_method="Adb"),
        ])
        monitor._device_sources = {"Adb": source}

        monitor.start_monitoring()

        self.assertTrue(monitor._running)
        self.assertIsNone(monitor._monitor_thread)
        self.assertEqual(source.poll_calls, 1)
        self.assertEqual(len(monitor.device_parser.sync_calls), 1)
        monitor.stop_monitoring()


if __name__ == "__main__":
    unittest.main()
