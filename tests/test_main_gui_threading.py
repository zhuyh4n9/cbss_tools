import importlib
import queue
import sys
import threading
import types
import unittest
from unittest import mock


def _load_main_gui_module():
    tkinter_module = types.ModuleType("tkinter")
    tkinter_ttk_module = types.ModuleType("tkinter.ttk")
    tkinter_messagebox_module = types.ModuleType("tkinter.messagebox")
    tkinter_filedialog_module = types.ModuleType("tkinter.filedialog")
    tkinter_simpledialog_module = types.ModuleType("tkinter.simpledialog")

    tkinter_module.ttk = tkinter_ttk_module
    tkinter_module.messagebox = tkinter_messagebox_module
    tkinter_module.filedialog = tkinter_filedialog_module
    tkinter_module.simpledialog = tkinter_simpledialog_module
    tkinter_module.TclError = RuntimeError

    fake_modules = {
        "tkinter": tkinter_module,
        "tkinter.ttk": tkinter_ttk_module,
        "tkinter.messagebox": tkinter_messagebox_module,
        "tkinter.filedialog": tkinter_filedialog_module,
        "tkinter.simpledialog": tkinter_simpledialog_module,
    }

    with mock.patch.dict(sys.modules, fake_modules):
        sys.modules.pop("src.main_gui", None)
        return importlib.import_module("src.main_gui")


class _FakeRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))


class _FakeConfig:
    def getboolean(self, *_args, **_kwargs):
        return False


class _FakeAuthManager:
    def is_auto_activation_enabled(self):
        return False

    def is_device_auto_activation_completed(self, _serial):
        return False

    def is_device_queued_for_auto_activation(self, _serial):
        return False


class _FakePromptManager:
    def get(self, key):
        return key

    def format(self, key, **kwargs):
        return f"{key}:{kwargs}"


class _FakeVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class TestMainGuiThreading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_gui = _load_main_gui_module()

    def _make_gui(self):
        gui = self.main_gui.AuthenticatorToolGUI.__new__(self.main_gui.AuthenticatorToolGUI)
        gui.root = _FakeRoot()
        gui._ui_task_queue = queue.Queue()
        gui.config_manager = _FakeConfig()
        gui.auth_manager = _FakeAuthManager()
        gui.prompt_mgr = _FakePromptManager()
        gui.status_var = _FakeVar()
        return gui

    def test_update_device_display_from_background_thread_waits_for_ui_drain(self):
        gui = self._make_gui()
        captured_rows = []
        gui._apply_device_rows = lambda rows: captured_rows.append(rows)

        device = self.main_gui.DeviceInfo(
            serial="SIM-0011",
            status="Authorized",
            device_type="target_device",
            uuid="uuid-001",
            usb_port="SIM",
        )

        worker = threading.Thread(target=gui.update_device_display, args=([device],))
        worker.start()
        worker.join()

        self.assertEqual(captured_rows, [])

        gui._drain_ui_task_queue()

        self.assertEqual(len(captured_rows), 1)
        self.assertEqual(captured_rows[0][0][0], "serial:SIM-0011")
        self.assertEqual(captured_rows[0][0][3], "Authorized")
        self.assertEqual(gui.root.after_calls[0][0], 16)

    def test_on_monitor_error_from_background_thread_waits_for_ui_drain(self):
        gui = self._make_gui()

        worker = threading.Thread(target=gui.on_monitor_error, args=("boom",))
        worker.start()
        worker.join()

        self.assertEqual(gui.status_var.value, "")

        gui._drain_ui_task_queue()

        self.assertEqual(
            gui.status_var.value,
            "Monitoring.monitor_error:{'error': 'boom'}",
        )


if __name__ == "__main__":
    unittest.main()
