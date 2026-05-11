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
        }

    def get(self, key):
        return self._values[key]


class _FakeAuthManager:
    def __init__(self, queued=False, completed=False):
        self._queued = queued
        self._completed = completed

    def is_device_queued_for_auto_activation(self, _serial):
        return self._queued

    def is_device_auto_activation_completed(self, _serial):
        return self._completed


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


if __name__ == "__main__":
    unittest.main()
