"""
构建选项（可在编译/打包时调整）
"""
import os


# 通过环境变量控制模拟设备功能（构建时可注入）
ENABLE_SIMULATED_DEVICE = os.environ.get("CBSS_ENABLE_SIMULATED_DEVICE", "0") == "1"
