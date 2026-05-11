# Agent Memory

## 2026-05-11

- 模拟设备开关 `CBSS_ENABLE_SIMULATED_DEVICE` 需要兼容多种真值写法（`1/true/yes/on`），避免现场环境变量格式差异导致功能未开启。
- TargetDevice 解析应避免高频重复执行：以 `DeviceMonitor` 连接索引变化为触发点，仅在设备连接状态变化、激活完成后的显式刷新及必要时机触发解析。
- ADB 设备轮询需保留 `adb devices -l` 的状态字段，供设备状态变化检测与解析节流使用。
- 设备探测流程需记录必要日志：连接变化 + 状态变化（serial/status/usb_port），并在 `add_simulated_device` 记录模拟设备创建信息，便于现场追踪。
