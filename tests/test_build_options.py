import unittest

from src.build_options import _env_flag_enabled


class TestBuildOptions(unittest.TestCase):
    def test_env_flag_enabled_accepts_common_truthy_values(self):
        for value in ("1", " true ", "YES", "On"):
            self.assertTrue(_env_flag_enabled(value))

    def test_env_flag_enabled_rejects_non_truthy_values(self):
        for value in ("0", "false", "off", "", None):
            self.assertFalse(_env_flag_enabled(value))


if __name__ == "__main__":
    unittest.main()
