import importlib
import queue
import sys
import threading
import types
import unittest
from unittest import mock


def _load_main_gui_module():
    fake_modules = {
        name: types.ModuleType(name)
        for name in (
            "tkinter",
            "tkinter.ttk",
            "tkinter.messagebox",
            "tkinter.filedialog",
            "tkinter.simpledialog",
        )
    }
    tkinter_module = fake_modules["tkinter"]
    tkinter_module.ttk = fake_modules["tkinter.ttk"]
    tkinter_module.messagebox = fake_modules["tkinter.messagebox"]
    tkinter_module.filedialog = fake_modules["tkinter.filedialog"]
    tkinter_module.simpledialog = fake_modules["tkinter.simpledialog"]
    tkinter_module.TclError = RuntimeError

    original_main_gui = sys.modules.pop("src.main_gui", None)
    with mock.patch.dict(sys.modules, fake_modules):
        module = importlib.import_module("src.main_gui")
    if original_main_gui is not None:
        sys.modules["src.main_gui"] = original_main_gui
    else:
        sys.modules.pop("src.main_gui", None)
    return module


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
    _SERIAL_COLUMN = 0
    _STATUS_COLUMN = 3

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

    def test_update_device_display_from_background_thread_queues_ui_task(self):
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
        self.assertEqual(captured_rows[0][0][self._SERIAL_COLUMN], f"serial:{device.serial}")
        self.assertEqual(captured_rows[0][0][self._STATUS_COLUMN], "Authorized")
        self.assertTrue(gui.root.after_calls)

    def test_on_monitor_error_from_background_thread_queues_ui_task(self):
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
