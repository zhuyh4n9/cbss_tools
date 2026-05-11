import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.adb_manager import ADBManager, CommandResult


class _FakeConfig:
    def get(self, section, key, default=None):
        return "adb"

    def get_adb_command(self, name, **kwargs):
        return "shell echo test"

    def get_status_message(self, code):
        return code


class TestAdbManagerIdentifierTrim(unittest.TestCase):
    def setUp(self):
        self.manager = ADBManager(_FakeConfig())

    @patch("src.adb_manager.subprocess.run")
    def test_get_connected_devices_trims_serial_spaces_and_tabs(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            stdout="List of devices attached\n  ABC123\tdevice usb:1-1 \n\tDEF456\tdevice usb:2-2\n",
            stderr="",
            returncode=0,
        )

        devices = self.manager.get_connected_devices()

        self.assertEqual([d.serial for d in devices], ["ABC123", "DEF456"])

    def test_get_device_uuid_trims_result_and_serial_input(self):
        with patch.object(self.manager, "execute_adb_command") as mock_exec:
            mock_exec.return_value = CommandResult(
                success=True,
                status_code=0,
                result_data=" \tUUID-001\t ",
                raw_output="",
            )

            result = self.manager.get_device_uuid(" \tSERIAL-001\t ")

            self.assertEqual(result.result_data, "UUID-001")
            mock_exec.assert_called_once_with("shell echo test", "SERIAL-001")


if __name__ == "__main__":
    unittest.main()
