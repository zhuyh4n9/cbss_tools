"""
测试：DeviceMonitor 统一管理 Simulator/ADB 设备
验证 SimulatorDevice 通过 Detector → DeviceMonitor → parser → UI 的完整流程
"""
import unittest
import threading
import time

from src.adb_manager import ADBManager, CommandResult, DeviceInfo, AuthenticatorInfo
from src.device_monitor import DeviceMonitor
from src.device_source import DeviceChange


class _FakeConfig:
    def get(self, section, key, default=''):
        return default
    def getint(self, section, key, default=0):
        return default
    def getboolean(self, section, key, default=False):
        return default
    def getfloat(self, section, key, default=0.0):
        return default


class _FakeAdbManager:
    def get_connected_devices(self):
        return []
    def get_device_uuid(self, serial):
        return CommandResult(success=False, status_code=1, error_message="N/A")
    def get_device_state(self, serial):
        return CommandResult(success=False, status_code=1, error_message="N/A")
    def get_authenticator_snapshot(self, serial):
        return CommandResult(success=False, status_code=1, error_message="N/A")


class TestDeviceMonitorSimDevice(unittest.TestCase):
    def setUp(self):
        self.config = _FakeConfig()
        self.adb = _FakeAdbManager()
        self.dm = DeviceMonitor(self.adb, self.config)
        # 启动parser worker线程（不启动monitor loop）
        self.dm.device_parser.start()
        self.ui_devices = []

        def capture_device_update(devices):
            self.ui_devices = list(devices)

        self.dm.add_callback('device_update', capture_device_update)

    def tearDown(self):
        self.dm.device_parser.stop(join_timeout=1.0)

    def _wait_parser(self, timeout=2.0):
        """等待parser worker处理完分类队列"""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.dm.device_parser._lock:
                if not self.dm.device_parser._classify_queue:
                    # 没有待分类设备，但worker可能还在处理await队列
                    time.sleep(0.05)
                    return
            time.sleep(0.05)

    def test_add_sim_device_appears_in_ui(self):
        """添加模拟设备后，UI 应该收到该设备"""
        device_info = self.dm.add_simulated_device("Unauthorized")
        serial = device_info.serial

        # 模拟monitor loop: 将detector变化同步到parser
        self.dm._update_device_info()
        self._wait_parser()

        self.assertGreater(len(self.ui_devices), 0,
                           "UI 应该收到设备列表更新")

        found = [d for d in self.ui_devices if d.serial == serial]
        self.assertEqual(len(found), 1,
                         f"设备 {serial} 应该在 UI 设备列表中")
        self.assertEqual(found[0].status, "Unauthorized")
        self.assertEqual(found[0].device_type, "target_device")
        self.assertTrue(found[0].uuid)

    def test_sim_device_activation_updates_ui(self):
        """激活模拟设备后，UI 应该更新状态"""
        device_info = self.dm.add_simulated_device("Unauthorized")
        serial = device_info.serial
        self.dm._update_device_info()
        self._wait_parser()

        self.dm.update_device_status(serial, "Authorized")

        found = [d for d in self.ui_devices if d.serial == serial]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].status, "Authorized")

    def test_sim_device_persists_across_cycles(self):
        """模拟设备在多个监控周期后不会消失"""
        device_info = self.dm.add_simulated_device("Unauthorized")
        serial = device_info.serial
        self.dm._update_device_info()
        self._wait_parser()

        # 模拟多次监控周期
        for _ in range(3):
            self.dm._update_device_info()
            found = [d for d in self.ui_devices if d.serial == serial]
            self.assertEqual(len(found), 1,
                             f"设备 {serial} 在第 {_+1} 次周期后消失了")

    def test_remove_sim_device(self):
        """移除模拟设备后，UI 不再显示"""
        device_info = self.dm.add_simulated_device("Unauthorized")
        serial = device_info.serial
        self.dm._update_device_info()
        self._wait_parser()

        for d in self.dm._detectors:
            if d.get_name() == "Simulator":
                d.remove_device(serial)
                break
        self.dm._update_device_info()

        found = [d for d in self.ui_devices if d.serial == serial]
        self.assertEqual(len(found), 0,
                         "移除后 UI 不应该再显示该设备")

    def test_get_target_device_for_sim(self):
        """get_target_device 能返回 SimulatorDevice"""
        device_info = self.dm.add_simulated_device("Unauthorized")
        serial = device_info.serial
        self.dm._update_device_info()
        self._wait_parser()

        target = self.dm.get_target_device(serial)
        self.assertIsNotNone(target)
        self.assertEqual(target.getSerialNumber(), serial)
        self.assertEqual(target.getStatus().lower(), "unauthorized")

    def test_get_device_auth_status_for_sim(self):
        """get_device_auth_status 能返回模拟设备状态"""
        device_info = self.dm.add_simulated_device("Unauthorized")
        serial = device_info.serial
        self.dm._update_device_info()
        self._wait_parser()

        status = self.dm.get_device_auth_status(serial)
        self.assertEqual(status.strip().lower(), "unauthorized")

    def test_sim_device_device_type_is_target_device(self):
        """模拟设备的 device_type 应该是 target_device（不是 unknown）"""
        device_info = self.dm.add_simulated_device("Unauthorized")
        self.dm._update_device_info()
        self._wait_parser()

        found = [d for d in self.ui_devices if d.serial == device_info.serial]
        self.assertEqual(found[0].device_type, "target_device",
                         "模拟设备 device_type 应为 target_device，否则 UI 会过滤掉")


if __name__ == "__main__":
    unittest.main()
