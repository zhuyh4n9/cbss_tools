#!/usr/bin/env python3
"""
认证器盒子PC Tool 主入口文件
"""
import sys
import os
import logging

from src.platform.compact import (
    acquire_single_instance,
    format_tkinter_import_error,
    get_compatibility_error_title,
    get_runtime_compatibility_error,
    release_single_instance,
    show_startup_error,
)

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


def main():
    """主函数"""
    single_instance_handle = None
    try:
        single_instance_handle = acquire_single_instance()
        if sys.platform == 'win32' and single_instance_handle is None:
            show_startup_error("提示", "The Cube 已在运行，请勿重复启动")
            sys.exit(1)

        # 检查Python版本
        if sys.version_info < (3, 6):
            show_startup_error("错误", "此程序需要Python 3.6或更高版本")
            sys.exit(1)

        compat_error = get_runtime_compatibility_error(project_root=os.getcwd())
        if compat_error:
            show_startup_error(get_compatibility_error_title(), compat_error)
            sys.exit(1)

        # 创建必要的目录
        os.makedirs('logs', exist_ok=True)
        os.makedirs('config', exist_ok=True)

        # 设置基本日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )

        try:
            import tkinter as tk
            from tkinter import messagebox
        except ImportError as exc:
            message = str(exc)
            if '_tkinter' in message or 'tkinter' in message:
                message = format_tkinter_import_error(exc)
            show_startup_error('启动错误', message)
            sys.exit(1)

        try:
            from src.main_gui import AuthenticatorToolGUI
        except ImportError as exc:
            message = f'导入模块失败: {exc}'
            if '_tkinter' in str(exc) or 'tkinter' in str(exc):
                message = format_tkinter_import_error(exc)
            show_startup_error('启动错误', message)
            sys.exit(1)

        # 启动GUI应用
        app = AuthenticatorToolGUI()
        app.run()

    except KeyboardInterrupt:
        print("\n程序被用户中断")
        sys.exit(0)
    except Exception as e:
        error_msg = f"程序启动失败: {str(e)}"
        print(error_msg)
        logging.error(error_msg)

        # 尝试显示错误对话框
        try:
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            messagebox.showerror("启动错误", error_msg)
        except Exception:
            show_startup_error("启动错误", error_msg)

        sys.exit(1)
    finally:
        release_single_instance(single_instance_handle)


if __name__ == "__main__":
    main()
