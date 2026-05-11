import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


class _FakePromptManager:
    def __init__(self):
        self._values = {
            "DeviceTable.action_manual_activate": "双击开始激活",
            "DeviceTable.action_unavailable": "无法进行激活",
            "DeviceTable.action_waiting_auto": "等待自动授权",
            "DeviceTable.action_auto_completed": "自动授权已完成",
            "DeviceTable.action_auto_queue_anomaly": "工具异常 -- 请提交Bug",
            "Common.confirm_title": "确认",
            "Common.success_title": "成功",
            "Common.fail_title": "失败",
            "Text.confirm_clear_log": "确定要清空日志吗？",
            "Text.log_cleared": "日志已清空",
            "MenuItems.clear_logs": "清空日志",
            "MenuItems.remove_simulated_device": "移除模拟设备",
            "InfoMessages.operation_success": "{name}执行成功",
            "InfoMessages.operation_fail": "{name}执行失败",
            "InfoMessages.simulated_device_removed": "模拟设备已移除: {serial}",
            "InfoMessages.simulated_device_remove_failed": "模拟设备移除失败: {serial}",
            "Text.confirm_remove_simulated_device": "确定移除模拟设备 {serial} 吗？",
            "Common.error_title": "错误",
        }

    def get(self, key):
        return self._values[key]

    def format(self, key, **kwargs):
        return self._values[key].format(**kwargs)


class _FakeAuthManager:
    def __init__(self, queued=False, completed=False, blocked=False):
        self._queued = queued
        self._completed = completed
        self._blocked = blocked

    def is_device_queued_for_auto_activation(self, _serial):
        return self._queued

    def is_device_auto_activation_completed(self, _serial):
        return self._completed

    def is_device_activation_blocked(self, _serial):
        return self._blocked


class _FakeStatusVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _FakeLogManager:
    def __init__(self, clear_result=True):
        self._clear_result = clear_result

    def clear_logs(self):
        return self._clear_result


class _FakeTargetDevice:
    def __init__(self, device_type):
        self._device_type = device_type

    def getType(self):
        return self._device_type


class _FakeDeviceMonitor:
    def __init__(self, device_type="SimulatorDevice", remove_result=True):
        self._target = _FakeTargetDevice(device_type)
        self._remove_result = remove_result
        self.removed_serials = []
        self.update_devices_calls = 0

    def get_target_device(self, _serial):
        return self._target

    def remove_simulated_device(self, serial):
        self.removed_serials.append(serial)
        return self._remove_result

    def update_devices(self):
        self.update_devices_calls += 1


class TestMainGuiDeviceAction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo_root = Path(__file__).resolve().parents[1]
        main_gui_path = repo_root / "src" / "main_gui.py"

        tkinter_module = types.ModuleType("tkinter")
        tkinter_ttk_module = types.ModuleType("tkinter.ttk")
        tkinter_messagebox_module = types.ModuleType("tkinter.messagebox")
        tkinter_filedialog_module = types.ModuleType("tkinter.filedialog")
        tkinter_simpledialog_module = types.ModuleType("tkinter.simpledialog")

        tkinter_module.ttk = tkinter_ttk_module
        tkinter_module.messagebox = tkinter_messagebox_module
        tkinter_module.filedialog = tkinter_filedialog_module
        tkinter_module.simpledialog = tkinter_simpledialog_module

        fake_modules = {
            "tkinter": tkinter_module,
            "tkinter.ttk": tkinter_ttk_module,
            "tkinter.messagebox": tkinter_messagebox_module,
            "tkinter.filedialog": tkinter_filedialog_module,
            "tkinter.simpledialog": tkinter_simpledialog_module,
        }

        with mock.patch.dict(sys.modules, fake_modules):
            module_globals = runpy.run_path(str(main_gui_path), run_name="__test__")
        cls.gui_class = module_globals["AuthenticatorToolGUI"]

    def test_auto_mode_unqueued_unauthorized_device_shows_bug_hint(self):
        gui = self.gui_class.__new__(self.gui_class)
        gui.prompt_mgr = _FakePromptManager()
        gui.auth_manager = _FakeAuthManager(queued=False, completed=False)

        heading = gui._resolve_device_action_heading(
            serial="D63532105C4A84F2AB00",
            status_lower="unauthorized",
            uuid_display="8bd957bdee...",
            auto_enabled=True,
        )

        self.assertEqual(heading, "工具异常 -- 请提交Bug")

    def test_blocked_device_shows_bug_hint_even_in_manual_mode(self):
        gui = self.gui_class.__new__(self.gui_class)
        gui.prompt_mgr = _FakePromptManager()
        gui.auth_manager = _FakeAuthManager(queued=False, completed=False, blocked=True)

        heading = gui._resolve_device_action_heading(
            serial="SIM-FAIL-LOCK-001",
            status_lower="unauthorized",
            uuid_display="8bd957bdee...",
            auto_enabled=False,
        )

        self.assertEqual(heading, "工具异常 -- 请提交Bug")

    def test_clear_logs_from_tools_menu_success(self):
        gui = self.gui_class.__new__(self.gui_class)
        gui.prompt_mgr = _FakePromptManager()
        gui.log_manager = _FakeLogManager(clear_result=True)
        gui.status_var = _FakeStatusVar()
        messagebox_module = self.gui_class.clear_logs_from_tools_menu.__globals__["messagebox"]

        with mock.patch.object(messagebox_module, "askyesno", return_value=True, create=True), \
             mock.patch.object(messagebox_module, "showinfo", create=True) as mock_showinfo:
            gui.clear_logs_from_tools_menu()

        self.assertEqual(gui.status_var.value, "日志已清空")
        mock_showinfo.assert_called_once()

    def test_clear_logs_from_tools_menu_cancelled(self):
        gui = self.gui_class.__new__(self.gui_class)
        gui.prompt_mgr = _FakePromptManager()
        gui.log_manager = _FakeLogManager(clear_result=True)
        gui.status_var = _FakeStatusVar()
        messagebox_module = self.gui_class.clear_logs_from_tools_menu.__globals__["messagebox"]

        with mock.patch.object(messagebox_module, "askyesno", return_value=False, create=True), \
             mock.patch.object(messagebox_module, "showinfo", create=True) as mock_showinfo, \
             mock.patch.object(messagebox_module, "showerror", create=True) as mock_showerror:
            gui.clear_logs_from_tools_menu()

        self.assertEqual(gui.status_var.value, "")
        mock_showinfo.assert_not_called()
        mock_showerror.assert_not_called()

    def test_remove_simulated_device_success(self):
        gui = self.gui_class.__new__(self.gui_class)
        gui.prompt_mgr = _FakePromptManager()
        gui.status_var = _FakeStatusVar()
        gui.device_monitor = _FakeDeviceMonitor(device_type="SimulatorDevice", remove_result=True)
        messagebox_module = self.gui_class.remove_simulated_device.__globals__["messagebox"]

        with mock.patch.object(messagebox_module, "askyesno", return_value=True, create=True), \
             mock.patch.object(messagebox_module, "showerror", create=True) as mock_showerror:
            removed = gui.remove_simulated_device("SIM-0001")

        self.assertTrue(removed)
        self.assertEqual(gui.device_monitor.removed_serials, ["SIM-0001"])
        self.assertEqual(gui.device_monitor.update_devices_calls, 1)
        self.assertEqual(gui.status_var.value, "模拟设备已移除: SIM-0001")
        mock_showerror.assert_not_called()

    def test_remove_simulated_device_rejects_non_simulator(self):
        gui = self.gui_class.__new__(self.gui_class)
        gui.prompt_mgr = _FakePromptManager()
        gui.status_var = _FakeStatusVar()
        gui.device_monitor = _FakeDeviceMonitor(device_type="AC8267Device", remove_result=True)
        messagebox_module = self.gui_class.remove_simulated_device.__globals__["messagebox"]

        with mock.patch.object(messagebox_module, "askyesno", create=True) as mock_askyesno:
            removed = gui.remove_simulated_device("DEV-0001")

        self.assertFalse(removed)
        self.assertEqual(gui.device_monitor.removed_serials, [])
        mock_askyesno.assert_not_called()


if __name__ == "__main__":
    unittest.main()
