import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from src.platform.compact import (
    acquire_single_instance,
    format_tkinter_import_error,
    get_compatibility_error_title,
    get_runtime_compatibility_error,
    get_runtime_profile,
    get_runtime_root_dir,
    release_single_instance,
    resolve_adb_path,
)


class TestPlatformCompact(unittest.TestCase):
    def test_get_runtime_profile_defaults_to_modern(self):
        profile = get_runtime_profile("unknown-mode")
        self.assertEqual(profile["mode"], "modern")
        self.assertEqual(profile["adb_source_dir"], "adb")

    def test_get_runtime_profile_returns_win7_profile(self):
        profile = get_runtime_profile("win7")
        self.assertEqual(profile["mode"], "win7")
        self.assertEqual(profile["adb_source_dir"], "adb_win7")
        self.assertEqual(profile["adb_server_port"], 5038)

    def test_resolve_adb_path_uses_runtime_specific_source_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            (root_dir / "adb_win7").mkdir(parents=True, exist_ok=True)
            resolved = resolve_adb_path("adb/adb.exe", mode="win7", project_root=str(root_dir))
            self.assertEqual(resolved, str((root_dir / "adb_win7" / "adb.exe").resolve()))

    def test_resolve_adb_path_keeps_modern_source_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            resolved = resolve_adb_path("adb/adb.exe", mode="modern", project_root=str(root_dir))
            self.assertEqual(resolved, str((root_dir / "adb" / "adb.exe").resolve()))

    def test_get_runtime_root_dir_prefers_frozen_executable_dir(self):
        with mock.patch("src.platform.compact.sys._MEIPASS", None, create=True):
            with mock.patch("src.platform.compact.sys.frozen", True, create=True):
                with mock.patch("src.platform.compact.sys.executable", r"D:\apps\TheCube.exe"):
                    with mock.patch("pathlib.Path.cwd", return_value=Path(r"D:\wrong-cwd")):
                        runtime_root = get_runtime_root_dir()
        self.assertEqual(runtime_root, Path(r"D:\apps"))

    def test_resolve_adb_path_uses_runtime_root_instead_of_cwd(self):
        with mock.patch("src.platform.compact.sys._MEIPASS", None, create=True):
            with mock.patch("src.platform.compact.sys.frozen", True, create=True):
                with mock.patch("src.platform.compact.sys.executable", r"D:\apps\TheCube.exe"):
                    with mock.patch("pathlib.Path.cwd", return_value=Path(r"D:\wrong-cwd")):
                        resolved = resolve_adb_path("adb/adb.exe", mode="win7")
        self.assertEqual(resolved, str(Path(r"D:\apps\adb\adb.exe").resolve()))

    def test_resolve_adb_path_keeps_packaged_adb_dir_for_frozen_win7(self):
        with mock.patch("src.platform.compact.sys._MEIPASS", r"D:\temp\_MEI123", create=True):
            with mock.patch("src.platform.compact.sys.frozen", True, create=True):
                with mock.patch("src.platform.compact.sys.executable", r"D:\apps\TheCube.exe"):
                    resolved = resolve_adb_path("adb/adb.exe", mode="win7")
        self.assertEqual(resolved, str(Path(r"D:\apps\adb\adb.exe").resolve()))

    def test_acquire_single_instance_returns_handle_on_first_launch(self):
        fake_kernel32 = mock.Mock()
        fake_kernel32.CreateMutexW.return_value = 101
        fake_kernel32.GetLastError.return_value = 0
        fake_ctypes = types.SimpleNamespace(
            windll=types.SimpleNamespace(kernel32=fake_kernel32),
            WinError=RuntimeError,
        )

        with mock.patch("sys.platform", "win32"):
            with mock.patch.dict("sys.modules", {"ctypes": fake_ctypes}):
                handle = acquire_single_instance("Local\\TestMutex")

        self.assertEqual(handle, 101)
        fake_kernel32.CloseHandle.assert_not_called()

    def test_acquire_single_instance_returns_none_when_already_running(self):
        fake_kernel32 = mock.Mock()
        fake_kernel32.CreateMutexW.return_value = 202
        fake_kernel32.GetLastError.return_value = 183
        fake_ctypes = types.SimpleNamespace(
            windll=types.SimpleNamespace(kernel32=fake_kernel32),
            WinError=RuntimeError,
        )

        with mock.patch("sys.platform", "win32"):
            with mock.patch.dict("sys.modules", {"ctypes": fake_ctypes}):
                handle = acquire_single_instance("Local\\TestMutex")

        self.assertIsNone(handle)
        fake_kernel32.CloseHandle.assert_called_once_with(202)

    def test_release_single_instance_closes_handle_on_windows(self):
        fake_kernel32 = mock.Mock()
        fake_ctypes = types.SimpleNamespace(
            windll=types.SimpleNamespace(kernel32=fake_kernel32),
            WinError=RuntimeError,
        )

        with mock.patch("sys.platform", "win32"):
            with mock.patch.dict("sys.modules", {"ctypes": fake_ctypes}):
                release_single_instance(303)

        fake_kernel32.CloseHandle.assert_called_once_with(303)

    def test_modern_tkinter_error_is_generic(self):
        message = format_tkinter_import_error(ImportError("modern error"), mode="modern")
        self.assertIn("程序无法加载 tkinter 运行环境", message)
        self.assertNotIn("KB2533623", message)

    def test_win7_tkinter_error_includes_patch_guidance(self):
        message = format_tkinter_import_error(ImportError("win7 error"), mode="win7")
        self.assertIn("KB2533623", message)
        self.assertIn("KB3063858", message)

    def test_get_compatibility_error_title_uses_platform_profile(self):
        self.assertEqual(get_compatibility_error_title("modern"), "平台兼容性错误")
        self.assertEqual(get_compatibility_error_title("win7"), "Windows 7 兼容性错误")

    def test_modern_runtime_compatibility_error_is_none(self):
        self.assertIsNone(get_runtime_compatibility_error(mode="modern"))

    def test_win7_runtime_compatibility_error_reports_missing_patch(self):
        compat_error = OSError("missing patch")
        compat_error.winerror = 127

        def raise_compat_error(_path):
            raise compat_error

        with mock.patch("sys.platform", "win32"):
            with mock.patch("sys.getwindowsversion", return_value=mock.Mock(major=6, minor=1), create=True):
                with mock.patch("os.getcwd", return_value="D:/workspace"):
                    with mock.patch("os.path.dirname", return_value="D:/workspace"):
                        with mock.patch("sys.executable", "D:/workspace/python.exe"):
                            with mock.patch("os.add_dll_directory", side_effect=raise_compat_error, create=True):
                                message = get_runtime_compatibility_error(mode="win7")
        self.assertIn("KB2533623", message)
        self.assertIn("KB3063858", message)


if __name__ == "__main__":
    unittest.main()