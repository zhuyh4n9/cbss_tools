RUNTIME_PROFILE = {
    "mode": "win7",
    "display_name": "Windows 7 SP1",
    "adb_source_dir": "adb_win7",
    "adb_server_port": 5038,
}


def get_runtime_compatibility_error(project_root=None):
    import os
    import sys

    if sys.platform != 'win32':
        return None

    version = sys.getwindowsversion()
    if (version.major, version.minor) > (6, 1):
        return None

    add_dll_directory = getattr(os, 'add_dll_directory', None)
    if add_dll_directory is None:
        return None

    probe_dir = getattr(sys, '_MEIPASS', None) or os.path.dirname(sys.executable) or os.getcwd()
    try:
        handle = add_dll_directory(probe_dir)
        if hasattr(handle, 'close'):
            handle.close()
        return None
    except OSError as exc:
        if getattr(exc, 'winerror', None) in (87, 127):
            return (
                '当前 Windows 7 系统缺少运行此程序所需的系统补丁，\n'
                '因此无法加载 Python 运行环境。\n\n'
                '请先在目标机器安装 Windows 7 补丁 KB2533623 或 KB3063858，\n'
                '安装完成后重新运行程序。'
            )
        return f'Win7 运行环境检查失败: {exc}'


def format_tkinter_import_error(exc):
    return (
        '程序无法加载 tkinter 运行环境。\n\n'
        '如果目标系统是 Windows 7，请先安装 KB2533623 或 KB3063858，\n'
        '安装完成后重新运行程序。\n\n'
        f'原始错误: {exc}'
    )


def get_compatibility_error_title():
    return 'Windows 7 兼容性错误'
