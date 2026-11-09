"""Platform runtime abstraction for compact target selection."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..build_options import CBSS_CUBE_COMPACT_MODE, normalize_compact_mode
from . import modern as modern_platform
from . import win7 as win7_platform


RUNTIME_PROFILES = {
    "modern": modern_platform.RUNTIME_PROFILE,
    "win7": win7_platform.RUNTIME_PROFILE,
}

PLATFORM_MODULES = {
    "modern": modern_platform,
    "win7": win7_platform,
}

SINGLE_INSTANCE_MUTEX_NAME = "Local\\TheCube_AC8267_Tool"


def get_runtime_root_dir(project_root: str = None) -> Path:
    if project_root:
        return Path(project_root)

    if getattr(sys, 'frozen', False):
        executable_path = getattr(sys, 'executable', '')
        if executable_path:
            return Path(executable_path).resolve().parent

    bundle_dir = getattr(sys, '_MEIPASS', None)
    if bundle_dir:
        return Path(bundle_dir)

    main_module = sys.modules.get('__main__')
    main_file = getattr(main_module, '__file__', '') if main_module else ''
    if main_file:
        return Path(main_file).resolve().parent

    executable_path = getattr(sys, 'executable', '')
    if executable_path:
        return Path(executable_path).resolve().parent

    return Path.cwd()


def get_runtime_profile(mode: str = None):
    normalized_mode = normalize_compact_mode(mode or CBSS_CUBE_COMPACT_MODE)
    return RUNTIME_PROFILES[normalized_mode]


def get_platform_module(mode: str = None):
    normalized_mode = normalize_compact_mode(mode or CBSS_CUBE_COMPACT_MODE)
    return PLATFORM_MODULES[normalized_mode]


def resolve_runtime_relative_path(relative_path: str, mode: str = None, project_root: str = None) -> str:
    runtime_profile = get_runtime_profile(mode)
    source_path = Path(relative_path)
    if source_path.is_absolute():
        return str(source_path)

    root_dir = get_runtime_root_dir(project_root)
    if source_path.parts and source_path.parts[0] == "adb" and not getattr(sys, 'frozen', False):
        source_path = Path(runtime_profile["adb_source_dir"], *source_path.parts[1:])

    return str((root_dir / source_path).resolve())


def resolve_adb_path(adb_path: str, mode: str = None, project_root: str = None) -> str:
    return resolve_runtime_relative_path(adb_path, mode=mode, project_root=project_root)


def get_runtime_compatibility_error(mode: str = None, project_root: str = None):
    return get_platform_module(mode).get_runtime_compatibility_error(project_root=project_root)


def format_tkinter_import_error(exc, mode: str = None) -> str:
    return get_platform_module(mode).format_tkinter_import_error(exc)


def get_compatibility_error_title(mode: str = None) -> str:
    return get_platform_module(mode).get_compatibility_error_title()


def acquire_single_instance(mutex_name: str = SINGLE_INSTANCE_MUTEX_NAME):
    if sys.platform != 'win32':
        return None

    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        raise ctypes.WinError()

    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return None

    return handle


def release_single_instance(handle) -> None:
    if sys.platform != 'win32' or not handle:
        return

    import ctypes

    ctypes.windll.kernel32.CloseHandle(handle)


def show_startup_error(title: str, message: str):
    """尽量在 tkinter 不可用时也给出可见错误提示。"""
    print(message)
    try:
        logs_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        with open(os.path.join(logs_dir, 'startup_error.txt'), 'w', encoding='utf-8') as error_file:
            error_file.write(f"{title}\n{message}\n")
    except Exception:
        pass

    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
        return
    except Exception:
        pass

    if sys.platform == 'win32':
        try:
            safe_title = title.replace('"', '""')
            safe_message = message.replace('"', '""').replace('\r\n', '\n').replace('\r', '\n')
            vb_message_lines = safe_message.split('\n')
            vb_message = ' & vbCrLf & '.join(f'"{line}"' for line in vb_message_lines) if vb_message_lines else '""'
            vb_lines = [
                'Dim title',
                'Dim message',
                f'title = "{safe_title}"',
                f'message = {vb_message}',
                'MsgBox message, 16, title',
            ]
            with tempfile.NamedTemporaryFile('w', suffix='.vbs', delete=False, encoding='utf-16') as script_file:
                script_file.write('\r\n'.join(vb_lines))
                script_path = script_file.name
            try:
                subprocess.run(['wscript.exe', script_path], check=False, capture_output=True)
            finally:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
        except Exception:
            pass