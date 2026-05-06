"""
构建选项（可在编译/打包时调整）
"""
import os


# 通过环境变量控制模拟设备功能（构建/运行时可注入）
# 示例: CBSS_ENABLE_SIMULATED_DEVICE=1 python package_all.py --type dev
ENABLE_SIMULATED_DEVICE = os.environ.get("CBSS_ENABLE_SIMULATED_DEVICE", "0") == "1"

# 模拟设备常量
SIMULATED_DEVICE_STATUS_OPTIONS = ("Pirated", "Authorized", "Unauthorized")
SIMULATED_AUTHENTICATOR_SERIAL = "SIMULATED_AUTHENTICATOR"
