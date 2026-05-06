#!/usr/bin/env python3
"""
认证器盒子PC Tool 主入口文件
"""
import sys
import os
import logging
import tkinter as tk
from tkinter import messagebox

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.main_gui import AuthenticatorToolGUI
except ImportError as e:
    print(f"导入模块失败: {e}")
    sys.exit(1)


def main():
    """主函数"""
    try:
        # 检查Python版本
        if sys.version_info < (3, 6):
            messagebox.showerror("错误", "此程序需要Python 3.6或更高版本")
            sys.exit(1)

        # 创建必要的目录
        os.makedirs('logs', exist_ok=True)
        os.makedirs('config', exist_ok=True)

        # 设置基本日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )

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
        except:
            pass

        sys.exit(1)


if __name__ == "__main__":
    main()
