# WiFi扫描功能故障排查指南

## 问题现象
用户报告WiFi扫描功能无法正常工作，出现错误。

## 已修复问题

### 1. 配置文件缺失WiFi扫描命令 ✅
**问题**: `config/default_config.ini` 中缺少 `wifi_start_scan` 和 `wifi_list_scan_results` 命令配置

**修复**: 已添加以下配置到 `[ADB_Commands]` 节:
```ini
wifi_start_scan = shell cmd wifi start-scan
wifi_list_scan_results = shell cmd wifi list-scan-results
```

## 诊断步骤

### 步骤1: 运行诊断脚本
```bash
python test_wifi_scan.py
```

诊断脚本会自动检查:
1. ✓ 配置文件是否正确加载
2. ✓ WiFi扫描命令是否已配置
3. ✓ ADB设备连接状态
4. ✓ WiFi命令是否能正常执行
5. ✓ 扫描结果能否正确解析

### 步骤2: 检查设备兼容性

WiFi扫描功能需要:
- **Android版本**: 8.0 (API 26) 或更高
- **WiFi硬件**: 设备必须有WiFi模块
- **ADB权限**: 需要shell访问权限

**验证方法**:
```bash
# 检查Android版本
adb shell getprop ro.build.version.sdk

# 检查是否支持cmd wifi命令
adb shell cmd wifi help

# 手动测试扫描
adb shell cmd wifi start-scan
adb shell cmd wifi list-scan-results
```

### 步骤3: 常见错误及解决方案

#### 错误1: "WiFi扫描启动失败"
**可能原因**:
- 设备不支持 `cmd wifi` 命令（Android版本太低）
- WiFi硬件不存在或被禁用

**解决方法**:
```bash
# 1. 检查WiFi状态
adb shell cmd wifi status

# 2. 尝试开启WiFi
adb shell cmd wifi set-wifi-enabled enabled

# 3. 再次尝试扫描
adb shell cmd wifi start-scan
```

#### 错误2: "扫描结果为空"
**可能原因**:
- 周围没有WiFi信号
- 扫描时间不够长
- 设备WiFi驱动问题

**解决方法**:
- 增加扫描等待时间（当前为3秒）
- 检查设备物理WiFi开关状态
- 重启设备WiFi模块

#### 错误3: "command not found" 或 "Unknown command"
**可能原因**:
- Android版本低于8.0
- 定制ROM不支持标准WiFi命令

**解决方法**:
- 升级Android系统
- 使用替代命令（部分设备支持）:
  ```bash
  adb shell wpa_cli scan
  adb shell wpa_cli scan_results
  ```

## 代码实现验证

### 配置文件检查
```bash
# 查看配置文件中的WiFi命令
cat config/default_config.ini | grep wifi_
```

应该看到:
```ini
wifi_enable = shell cmd wifi set-wifi-enabled enabled
wifi_disable = shell cmd wifi set-wifi-enabled disabled
wifi_connect = shell cmd wifi connect-network "{ssid}" {security} "{password}"
wifi_start_scan = shell cmd wifi start-scan
wifi_list_scan_results = shell cmd wifi list-scan-results
```

### 代码实现检查
WiFi扫描功能实现位置:
- **ADB Manager** (`src/adb_manager.py`):
  - `wifi_scan(serial)` - 第284行
  - `parse_wifi_scan_results(raw_output)` - 第320行
  
- **GUI对话框** (`src/main_gui.py`):
  - `WifiScanDialog` 类 - 第1721行
  - `scan_and_connect_wifi()` 方法 - 第804行

## 功能特性

### 扫描流程
1. 开启WiFi（如果未开启）
2. 发送扫描命令 `cmd wifi start-scan`
3. 等待3秒让扫描完成
4. 获取结果 `cmd wifi list-scan-results`
5. 解析并显示网络列表

### 扫描结果显示
- **SSID**: WiFi网络名称
- **信号强度**: dBm值 + 等级（优秀/良好/一般/差）
- **频段**: 2.4G / 5G
- **加密方式**: Open / WEP / WPA / WPA2 / WPA3
- **BSSID**: MAC地址

### 连接功能
- 双击WiFi列表项即可连接
- 自动判断是否需要密码
- 自动保存WiFi历史记录
- 支持多种加密方式

## 手动测试流程

### 测试1: 基本扫描测试
```bash
# 1. 连接设备
adb devices

# 2. 开启WiFi
adb shell cmd wifi set-wifi-enabled enabled

# 3. 启动扫描
adb shell cmd wifi start-scan

# 4. 等待3秒
# (等待...)

# 5. 查看结果
adb shell cmd wifi list-scan-results
```

### 测试2: GUI功能测试
1. 启动程序
2. 点击菜单: **工具 → 🔍 扫描并连接WiFi**
3. 选择设备（如果有多个）
4. 点击"🔄 扫描WiFi"按钮
5. 观察扫描状态和结果
6. 选择WiFi网络
7. 输入密码（如需要）
8. 双击或点击"连接选中WiFi"

## 预期输出示例

### 成功的扫描结果
```
SSID                BSSID               Frequency Signal Capabilities
ATC_SD5_5G          aa:bb:cc:dd:ee:ff   5180     -45    [WPA2-PSK-CCMP][ESS]
Home-WiFi           11:22:33:44:55:66   2437     -52    [WPA2-PSK-CCMP][WPS][ESS]
Guest-Network       77:88:99:aa:bb:cc   2462     -67    [WPA2-PSK-CCMP][ESS]
```

### 解析后的数据
```
网络1:
  SSID: ATC_SD5_5G
  信号: -45dBm (优秀)
  频段: 5G
  加密: WPA2
  MAC: aa:bb:cc:dd:ee:ff

网络2:
  SSID: Home-WiFi
  信号: -52dBm (良好)
  频段: 2.4G
  加密: WPA2
  MAC: 11:22:33:44:55:66
```

## 替代方案

如果设备不支持 `cmd wifi` 命令，可以考虑以下替代方案:

### 方案1: 使用wpa_cli (需要root)
```bash
adb shell su -c "wpa_cli scan"
adb shell su -c "wpa_cli scan_results"
```

### 方案2: 使用dumpsys wifi
```bash
adb shell dumpsys wifi | grep -A 20 "Latest scan results"
```

### 方案3: 降级功能
- 仅保留手动输入SSID功能
- 显示当前已连接的WiFi信息
- 提供历史记录快速选择

## 联系与反馈

如果问题仍未解决，请提供以下信息:
1. 设备型号和Android版本
2. 运行 `test_wifi_scan.py` 的完整输出
3. 手动执行ADB命令的结果
4. 错误截图或日志

## 更新日志

- **2024-01-XX**: 修复配置文件缺失WiFi扫描命令
- **2024-01-XX**: 创建诊断脚本和故障排查指南
