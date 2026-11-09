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
                self.assertIn("collect_submodules('src')", content)
                self.assertIn("'tkinter.simpledialog'", content)
            finally:
                self.packager.project_root = self.repo_root
                os.chdir(cwd)

    def test_win7_target_uses_isolated_spec_and_output_dirs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = Path.cwd()
            try:
                temp_path = Path(tmp_dir)
                packager = CBSSPackager(target_os="win7")
                packager.project_root = temp_path
                packager.log = lambda *args, **kwargs: None
                (temp_path / "adb_win7").mkdir(parents=True, exist_ok=True)
                os.chdir(temp_path)
                with mock.patch("os.path.exists", return_value=False):
                    spec_name = packager.create_pyinstaller_spec(simple=False)
                spec_path = temp_path / spec_name
                self.assertEqual(spec_name, "TheCube_win7.spec")
                self.assertIn("TheCube_Portable_Win7", packager.build_dirs["portable"])
                self.assertEqual(packager.requirements_file, "requirements-win7.txt")
                content = spec_path.read_text(encoding="utf-8")
                self.assertIn("upx=False", content)
                self.assertIn("runtime_hooks=[", content)
                self.assertIn("pyi_rth_compact_mode.py", content)
                self.assertIn("adb_win7/adb.exe", content)
            finally:
                os.chdir(cwd)

    def test_win7_build_uses_python37_launcher(self):
        packager = CBSSPackager(target_os="win7")
        packager.log = lambda *args, **kwargs: None

        def fake_probe(cmd):
            return (3, 7, 9) if cmd == ["py", "-3.7"] else None

        with mock.patch.object(packager, "_probe_python_version", side_effect=fake_probe):
            with mock.patch.object(packager, "_tkinter_exists_in_target_python", return_value=True):
                self.assertTrue(packager.check_environment(require_build=True))
                self.assertEqual(packager._target_python_cmd, ["py", "-3.7"])

    def test_win7_build_reports_missing_python37(self):
        packager = CBSSPackager(target_os="win7")
        packager.log = lambda *args, **kwargs: None
        with mock.patch.object(packager, "_probe_python_version", return_value=None):
            self.assertFalse(packager.check_environment(require_build=True))

    def test_win7_build_dependencies_checked_in_target_python(self):
        packager = CBSSPackager(target_os="win7")
        packager.log = lambda *args, **kwargs: None
        with mock.patch.object(packager, "_resolve_target_python", return_value=True):
            packager._target_python_cmd = ["py", "-3.7"]
            packager._target_python_version = (3, 7, 9)
            with mock.patch.object(packager, "_module_exists_in_target_python", return_value=True):
                with mock.patch.object(packager, "_tkinter_exists_in_target_python", return_value=True):
                    self.assertTrue(packager.check_build_dependencies())

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
