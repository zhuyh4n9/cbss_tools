RUNTIME_PROFILE = {
    "mode": "modern",
    "display_name": "Windows 10/11",
    "adb_source_dir": "adb",
    "adb_server_port": 5037,
}


def get_runtime_compatibility_error(project_root=None):
    return None


def format_tkinter_import_error(exc):
    return (
        '程序无法加载 tkinter 运行环境。\n\n'
        f'原始错误: {exc}'
    )


def get_compatibility_error_title():
    return '平台兼容性错误'
