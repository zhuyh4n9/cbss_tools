import unittest

from src.adb_manager import ADBManager, CommandResult


class _FakeConfig:
    def get(self, section, key, default=''):
        if section == 'General' and key == 'adb_path':
            return 'adb/adb.exe'
        return default

    def get_status_message(self, status_code):
        return f"Status_{status_code}"


class TestADBManagerParseOutput(unittest.TestCase):
    def setUp(self):
        self.adb = ADBManager(_FakeConfig())

    def test_parse_success_output(self):
        output = "[status] 0\n[result] some_data\n"
        result = self.adb._parse_command_output(output, True)
        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 0)
        self.assertEqual(result.result_data, "some_data")

    def test_parse_failure_status_code(self):
        output = "[status] -1, error occurred\n"
        result = self.adb._parse_command_output(output, True)
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, -1)
        self.assertEqual(result.error_message, "error occurred")

    def test_parse_command_not_found(self):
        output = "some output\ncommand not found\n"
        result = self.adb._parse_command_output(output, True)
        self.assertFalse(result.success)
        self.assertIn("not found", result.error_message)

    def test_parse_permission_denied(self):
        output = "Permission denied\n"
        result = self.adb._parse_command_output(output, True)
        self.assertFalse(result.success)
        self.assertIn("Permission denied", result.error_message)

    def test_parse_no_status_line(self):
        output = "just some random output\n"
        result = self.adb._parse_command_output(output, True)
        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 0)

    def test_parse_no_status_line_command_failed(self):
        output = "just some random output\n"
        result = self.adb._parse_command_output(output, False)
        self.assertFalse(result.success)

    def test_parse_multiple_status_lines(self):
        output = "[status] 0\n[status] -1, real error\n[result] data\n"
        result = self.adb._parse_command_output(output, True)
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, -1)
        self.assertEqual(result.error_message, "real error")
        self.assertEqual(result.result_data, "data")

    def test_parse_status_without_message(self):
        output = "[status] 5\n[result] payload\n"
        result = self.adb._parse_command_output(output, True)
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 5)
        self.assertEqual(result.error_message, "Status_5")

    def test_parse_result_without_status(self):
        output = "[result] only_result\n"
        result = self.adb._parse_command_output(output, True)
        self.assertTrue(result.success)
        self.assertEqual(result.result_data, "only_result")

    def test_parse_empty_output(self):
        result = self.adb._parse_command_output("", True)
        self.assertTrue(result.success)
        self.assertEqual(result.status_code, 0)

    def test_parse_not_found_pattern(self):
        output = "sh: some_tool: not found\n"
        result = self.adb._parse_command_output(output, True)
        self.assertFalse(result.success)

    def test_parse_no_such_file(self):
        output = "No such file or directory\n"
        result = self.adb._parse_command_output(output, True)
        self.assertFalse(result.success)

    def test_command_result_dataclass(self):
        cr = CommandResult(success=True, status_code=0, result_data="ok", error_message="", raw_output="raw")
        self.assertTrue(cr.success)
        self.assertEqual(cr.status_code, 0)
        self.assertEqual(cr.result_data, "ok")
        self.assertEqual(cr.raw_output, "raw")


if __name__ == "__main__":
    unittest.main()