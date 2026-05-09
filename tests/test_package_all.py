import tempfile
import unittest
import os
from pathlib import Path
from unittest import mock

from package_all import CBSSPackager


class TestPackageAll(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        self.packager = CBSSPackager()
        self.packager.project_root = self.repo_root

    def test_create_pyinstaller_spec_includes_prompt_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = Path.cwd()
            try:
                temp_path = Path(tmp_dir)
                self.packager.project_root = temp_path
                self.packager.log = lambda *args, **kwargs: None
                os.chdir(temp_path)
                with mock.patch("os.path.exists", return_value=False):
                    spec_name = self.packager.create_pyinstaller_spec(simple=True)
                spec_path = temp_path / spec_name
                self.assertTrue(spec_path.exists())
                content = spec_path.read_text(encoding="utf-8")
                self.assertIn("('config/prompt_chn.ini', 'config')", content)
            finally:
                self.packager.project_root = self.repo_root
                os.chdir(cwd)

    def test_check_build_dependencies_reports_missing_modules(self):
        with mock.patch("package_all.importlib.util.find_spec", return_value=None):
            self.assertFalse(self.packager.check_build_dependencies())

    def test_create_dev_scripts_creates_setup_venv_alias(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dev_dir = Path(tmp_dir)
            self.packager._create_dev_scripts(dev_dir)
            self.assertTrue((dev_dir / "setup_dev.bat").exists())
            setup_venv = dev_dir / "setup_venv.bat"
            self.assertTrue(setup_venv.exists())
            self.assertIn("call setup_dev.bat", setup_venv.read_text(encoding="gbk"))


if __name__ == "__main__":
    unittest.main()
