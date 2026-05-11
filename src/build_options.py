"""
构建选项（可在编译/打包时调整）
"""
import os


# 通过环境变量控制模拟设备功能（构建/运行时可注入）
# 示例: CBSS_ENABLE_SIMULATED_DEVICE=1 python package_all.py --type dev
def _env_flag_enabled(value: str) -> bool:
    if value is None:
        return False
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


ENABLE_SIMULATED_DEVICE = _env_flag_enabled(os.environ.get("CBSS_ENABLE_SIMULATED_DEVICE", "0"))

# 模拟设备常量
SIMULATED_DEVICE_STATUS_OPTIONS = ("Pirated", "Authorized", "Unauthorized", "AuthorizationFailure")
SIMULATED_AUTHENTICATOR_SERIAL = "SIMULATED_AUTHENTICATOR"
