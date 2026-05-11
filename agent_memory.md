# Agent Memory

## 2026-05-11
- 设备探测相关标识统一做 trim：
  - `serial` 在设备列表解析时按空白分割并去除首尾空格/tab。
  - `uuid` 在 `get_device_uuid()` 成功返回后去除首尾空格/tab。
- DeviceMonitor 仅在连接状态变化时同步到 DeviceParser，避免周期性重复触发 TargetDevice 解析。
- 模拟设备开关支持多种真值写法：`1/true/yes/on/enable/enabled`。
