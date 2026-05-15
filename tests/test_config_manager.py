import os
import tempfile
import unittest

from src.config_manager import ConfigManager


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.tmpdir.name, "test_config.ini")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_config(self, content):
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_load_config_file(self):
        self._write_config("[General]\nrefresh_rate=5\nadb_path=adb/adb.exe\n")
        cm = ConfigManager(self.config_path)
        self.assertEqual(cm.getint("General", "refresh_rate"), 5)
        self.assertEqual(cm.get("General", "adb_path"), "adb/adb.exe")

    def test_load_nonexistent_config_falls_back_to_default(self):
        cm = ConfigManager(os.path.join(self.tmpdir.name, "nonexistent.ini"))
        self.assertEqual(cm.get("General", "adb_path"), "adb/adb.exe")

    def test_get_with_fallback(self):
        cm = ConfigManager(self.config_path)
        self.assertEqual(cm.get("Nonexistent", "key", "default_val"), "default_val")

    def test_getint_with_fallback(self):
        cm = ConfigManager(self.config_path)
        self.assertEqual(cm.getint("Nonexistent", "key", 42), 42)

    def test_getfloat_with_fallback(self):
        cm = ConfigManager(self.config_path)
        self.assertAlmostEqual(cm.getfloat("Nonexistent", "key", 3.14), 3.14)

    def test_getboolean_with_fallback(self):
        cm = ConfigManager(self.config_path)
        self.assertTrue(cm.getboolean("Nonexistent", "key", True))
        self.assertFalse(cm.getboolean("Nonexistent", "key2", False))

    def test_set_and_save(self):
        cm = ConfigManager(self.config_path)
        cm.set("TestSection", "test_key", "test_value")
        cm.save_config()
        cm2 = ConfigManager(self.config_path)
        self.assertEqual(cm2.get("TestSection", "test_key"), "test_value")

    def test_get_section(self):
        self._write_config("[SectionA]\nkey1=val1\nkey2=val2\n")
        cm = ConfigManager(self.config_path)
        section = cm.get_section("SectionA")
        self.assertEqual(section, {"key1": "val1", "key2": "val2"})

    def test_get_status_message(self):
        self._write_config("[Status_Messages]\n1=error_one\n")
        cm = ConfigManager(self.config_path)
        self.assertEqual(cm.get_status_message("1"), "error_one")
        self.assertIn("未知", cm.get_status_message("999"))

    def test_get_adb_command(self):
        self._write_config("[ADB_Commands]\ndevice_uuid=shell get_uuid {param}\n")
        cm = ConfigManager(self.config_path)
        cmd = cm.get_adb_command("device_uuid", param="test")
        self.assertEqual(cmd, "shell get_uuid test")

    def test_get_adb_command_no_template(self):
        cm = ConfigManager(self.config_path)
        self.assertEqual(cm.get_adb_command("nonexistent"), "")

    def test_save_and_get_wifi_history(self):
        cm = ConfigManager(self.config_path)
        cm.save_wifi_history("MySSID", "pass123", "wpa2")
        history = cm.get_wifi_history()
        self.assertEqual(history["ssid"], "MySSID")
        self.assertEqual(history["password"], "pass123")
        self.assertEqual(history["security"], "wpa2")

    def test_getboolean_parses_values(self):
        self._write_config("[Flags]\nenabled=true\ndisabled=false\n")
        cm = ConfigManager(self.config_path)
        self.assertTrue(cm.getboolean("Flags", "enabled"))
        self.assertFalse(cm.getboolean("Flags", "disabled"))

    def test_getint_parses_values(self):
        self._write_config("[Numbers]\ncount=42\n")
        cm = ConfigManager(self.config_path)
        self.assertEqual(cm.getint("Numbers", "count"), 42)

    def test_getfloat_parses_values(self):
        self._write_config("[Numbers]\nratio=0.75\n")
        cm = ConfigManager(self.config_path)
        self.assertAlmostEqual(cm.getfloat("Numbers", "ratio"), 0.75)

    def test_migrates_legacy_pirated_color_default(self):
        self._write_config("[DeviceList]\ncolor_pirated=#FFD700\n")
        cm = ConfigManager(self.config_path)
        self.assertEqual(cm.get("DeviceList", "color_pirated"), "#8B4513")

    def test_preserves_custom_pirated_color(self):
        self._write_config("[DeviceList]\ncolor_pirated=#663300\n")
        cm = ConfigManager(self.config_path)
        self.assertEqual(cm.get("DeviceList", "color_pirated"), "#663300")


if __name__ == "__main__":
    unittest.main()