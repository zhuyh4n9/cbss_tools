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
        self.options = {}

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))

    def configure(self, **kwargs):
        self.options.update(kwargs)


class _FakeConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def getboolean(self, *_args, **_kwargs):
        key = (_args[0], _args[1]) if len(_args) >= 2 else None
        return self.values.get(key, False)

    def getint(self, *_args, **_kwargs):
        key = (_args[0], _args[1]) if len(_args) >= 2 else None
        return self.values.get(key, 10)

    def get(self, *_args, **_kwargs):
        key = (_args[0], _args[1]) if len(_args) >= 2 else None
        return self.values.get(key, '#000000')

    def set(self, section, key, value):
        self.values[(section, key)] = value

    def save_config(self, *_args, **_kwargs):
        return True


class _FakeAuthManager:
    def is_auto_activation_enabled(self):
        return False

    def is_device_auto_activation_completed(self, _serial):
        return False

    def is_device_queued_for_auto_activation(self, _serial):
        return False


class _FakePromptManager:
    values = {
        "DeviceTable.uuid_fetching": "UUID加载中",
        "DeviceTable.uuid_unavailable": "UUID不可用",
        "DeviceStatus.Checking": "检测中",
    }

    def get(self, key, default=None, fallback=None):
        if key in self.values:
            return self.values[key]
        return fallback if fallback is not None else (default if default is not None else key)

    def format(self, key, **kwargs):
        return f"{key}:{kwargs}"


class _FakeVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeLabel:
    def __init__(self):
        self.options = {}

    def config(self, **kwargs):
        self.options.update(kwargs)


class _FakeTree:
    def __init__(self):
        self.tags = {}

    def tag_configure(self, tag, **kwargs):
        self.tags[tag] = kwargs


class _FakeStyle:
    def __init__(self, maps=None):
        self.configured = {}
        self.maps = {}
        self.source_maps = maps or {}
        self.current_theme = "default"
        self.available_themes = ["clam", "vista", "alt"]

    def configure(self, style_name, **kwargs):
        self.configured[style_name] = kwargs

    def map(self, style_name, query_opt=None, **kwargs):
        if query_opt is not None:
            return self.source_maps.get((style_name, query_opt), [])
        self.maps.setdefault(style_name, {}).update(kwargs)

    def theme_names(self):
        return tuple(self.available_themes)

    def theme_use(self, theme_name=None):
        if theme_name is None:
            return self.current_theme
        self.current_theme = theme_name

    def theme_create(self, theme_name, parent=None):
        if theme_name not in self.available_themes:
            self.available_themes.append(theme_name)

    def lookup(self, style_name, option):
        return ""


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

    def test_update_device_display_uses_configured_uuid_placeholders(self):
        gui = self._make_gui()
        captured_rows = []
        gui._apply_device_rows = lambda rows: captured_rows.append(rows)

        devices = [
            self.main_gui.DeviceInfo(
                serial="SIM-UNKNOWN",
                status="Unknown",
                device_type="unknown",
                uuid="",
                usb_port="SIM",
            ),
            self.main_gui.DeviceInfo(
                serial="SIM-PENDING",
                status="Unauthorized",
                device_type="target_device",
                uuid="",
                usb_port="SIM",
            ),
        ]

        gui.config_manager = _FakeConfig({("UI", "show_na_devices"): True})
        gui.update_device_display(devices)

        self.assertEqual(captured_rows[0][0][1], "UUID不可用")
        self.assertEqual(captured_rows[0][1][1], "UUID加载中")

    def test_is_uuid_ready_uses_configured_prompt_placeholders(self):
        gui = self._make_gui()

        self.assertFalse(gui._is_uuid_ready("UUID加载中"))
        self.assertFalse(gui._is_uuid_ready("UUID不可用"))
        self.assertFalse(gui._is_uuid_ready("检测中"))
        self.assertTrue(gui._is_uuid_ready("550e8400-e29b-41d4-a716-446655440000"))

    def test_setup_device_tree_tags_uses_device_list_config(self):
        gui = self._make_gui()
        gui.config_manager = _FakeConfig({
            ("DeviceList", "font_size"): 18,
            ("DeviceList", "font_bold"): True,
            ("DeviceList", "color_authorized"): "#00AA00",
            ("DeviceList", "color_unauthorized"): "#111111",
            ("DeviceList", "color_authorization_failure"): "#AA0000",
            ("DeviceList", "color_pirated"): "#CCCC00",
        })
        gui.device_tree = _FakeTree()
        fake_style = _FakeStyle({
            ("Treeview", "foreground"): [
                ("disabled", "#888888"),
                ("!disabled", "!selected", "#000000"),
                ("selected", "#FFFFFF"),
            ],
            ("Treeview", "background"): [
                ("!disabled", "!selected", "#FFFFFF"),
                ("selected", "#0078D7"),
            ],
        })

        with mock.patch.object(self.main_gui.ttk, "Style", return_value=fake_style, create=True):
            gui._setup_device_tree_tags()

        item_font = ("TkDefaultFont", 18, "bold")
        self.assertEqual(fake_style.configured["DeviceList.Treeview"]["font"], item_font)
        self.assertEqual(fake_style.configured["DeviceList.Treeview.Heading"]["font"], item_font)
        self.assertNotIn(
            ("!disabled", "!selected", "#000000"),
            fake_style.maps["DeviceList.Treeview"]["foreground"],
        )
        self.assertIn(
            ("selected", "#FFFFFF"),
            fake_style.maps["DeviceList.Treeview"]["foreground"],
        )
        self.assertIn(
            ("disabled", "#888888"),
            fake_style.maps["DeviceList.Treeview"]["foreground"],
        )
        self.assertEqual(gui.device_tree.tags["authorized"]["foreground"], "#00AA00")
        self.assertEqual(gui.device_tree.tags["pirated"]["foreground"], "#CCCC00")

    def test_cube_status_info_style_uses_configured_font_and_colors(self):
        gui = self._make_gui()
        gui.config_manager = _FakeConfig({
            ("CubeStatusInfo", "font_size"): 16,
            ("CubeStatusInfo", "authorized_count_color"): "#123456",
            ("CubeStatusInfo", "remaining_low_color"): "#AA0000",
            ("CubeStatusInfo", "remaining_medium_color"): "#AA7700",
            ("CubeStatusInfo", "remaining_high_color"): "#00AA00",
        })
        gui.counter_var = _FakeVar("75")
        gui.expire_date_label = _FakeLabel()
        gui.counter_label = _FakeLabel()
        gui.authorized_num_label = _FakeLabel()
        gui.device_status_label = _FakeLabel()
        gui.time_status_label = _FakeLabel()
        gui.network_status_label = _FakeLabel()
        gui.wifi_ssid_label = _FakeLabel()

        gui._setup_cube_status_info_style()

        self.assertEqual(gui.counter_label.options["font"], ("TkDefaultFont", 16))
        self.assertEqual(gui.device_status_label.options["font"], ("TkDefaultFont", 16))
        self.assertEqual(gui.authorized_num_label.options["foreground"], "#123456")
        self.assertEqual(gui.counter_label.options["foreground"], "#AA7700")

    def test_remaining_count_color_thresholds(self):
        gui = self._make_gui()
        gui.config_manager = _FakeConfig({
            ("CubeStatusInfo", "remaining_low_color"): "#LOW",
            ("CubeStatusInfo", "remaining_medium_color"): "#MED",
            ("CubeStatusInfo", "remaining_high_color"): "#HIGH",
        })

        self.assertEqual(gui._get_remaining_count_color(49), "#LOW")
        self.assertEqual(gui._get_remaining_count_color(50), "#MED")
        self.assertEqual(gui._get_remaining_count_color(99), "#MED")
        self.assertEqual(gui._get_remaining_count_color(100), "#HIGH")

    def test_apply_custom_theme_uses_clam_base_and_palette(self):
        gui = self._make_gui()
        gui.config_manager = _FakeConfig({("Theme", "current"): "dark"})
        fake_style = _FakeStyle()

        with mock.patch.object(self.main_gui.ttk, "Style", return_value=fake_style, create=True):
            applied = gui.apply_configured_theme()

        self.assertEqual(applied, "dark")
        self.assertEqual(fake_style.current_theme, "cbss-dark")
        self.assertEqual(fake_style.configured["TFrame"]["background"], "#202124")
        self.assertEqual(fake_style.configured["Treeview"]["foreground"], "#E8EAED")
        self.assertEqual(gui.root.options["bg"], "#202124")

    def test_theme_alias_and_change_theme_persist_config(self):
        gui = self._make_gui()
        gui.config_manager = _FakeConfig()
        gui.theme_menu_var = _FakeVar()
        fake_style = _FakeStyle()

        with mock.patch.object(self.main_gui.ttk, "Style", return_value=fake_style, create=True):
            gui.change_theme("moderm")

        self.assertEqual(gui.config_manager.values[("Theme", "current")], "modern")
        self.assertEqual(gui.theme_menu_var.value, "modern")
        self.assertEqual(fake_style.current_theme, "cbss-modern")

    def test_native_theme_uses_available_ttk_theme(self):
        gui = self._make_gui()
        fake_style = _FakeStyle()

        with mock.patch.object(self.main_gui.ttk, "Style", return_value=fake_style, create=True):
            applied = gui._apply_theme("vista")

        self.assertEqual(applied, "vista")
        self.assertEqual(fake_style.current_theme, "vista")

    def test_selectable_themes_include_custom_and_native_themes(self):
        gui = self._make_gui()
        fake_style = _FakeStyle()

        with mock.patch.object(self.main_gui.ttk, "Style", return_value=fake_style, create=True):
            themes = gui._get_selectable_themes()

        self.assertEqual(themes[:4], ("modern", "aero", "light", "dark"))
        self.assertIn("clam", themes)
        self.assertIn("vista", themes)
        self.assertIn("alt", themes)

    def test_aero_theme_uses_screenshot_like_palette(self):
        gui = self._make_gui()
        gui.config_manager = _FakeConfig({("Theme", "current"): "aero"})
        fake_style = _FakeStyle()

        with mock.patch.object(self.main_gui.ttk, "Style", return_value=fake_style, create=True):
            applied = gui.apply_configured_theme()

        self.assertEqual(applied, "aero")
        self.assertEqual(fake_style.current_theme, "cbss-aero")
        self.assertEqual(fake_style.configured["TFrame"]["background"], "#EEF3FA")
        self.assertEqual(fake_style.configured["Treeview"]["fieldbackground"], "#FFFFFF")
        self.assertEqual(gui.root.options["bg"], "#EEF3FA")

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
