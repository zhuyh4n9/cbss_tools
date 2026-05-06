# WiFi扫描功能测试脚本

## 快速测试

### 测试1：验证配置文件

```powershell
# 检查配置文件中是否有扫描命令
Get-Content config\default_config.ini | Select-String "wifi_start_scan"
Get-Content config\default_config.ini | Select-String "wifi_list_scan_results"
```

**预期输出**：
```
wifi_start_scan = shell cmd wifi start-scan
wifi_list_scan_results = shell cmd wifi list-scan-results
```

---

### 测试2：手动ADB扫描

```powershell
# 获取设备列表
adb devices

# 扫描WiFi（替换YOUR_DEVICE_SERIAL）
$device = "YOUR_DEVICE_SERIAL"

adb -s $device shell cmd wifi set-wifi-enabled enabled
Start-Sleep -Seconds 1

adb -s $device shell cmd wifi start-scan
Write-Host "等待扫描完成..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

adb -s $device shell cmd wifi list-scan-results
```

---

### 测试3：Python功能测试

创建测试脚本 `test_wifi_scan.py`:

```python
import sys
sys.path.insert(0, 'src')

from config_manager import ConfigManager
from adb_manager import ADBManager

# 初始化
config = ConfigManager()
adb = ADBManager(config)

# 获取设备
devices = adb.get_connected_devices()
if not devices:
    print("❌ 未检测到设备")
    exit(1)

device_serial = devices[0].serial
print(f"✅ 使用设备: {device_serial}")

# 执行扫描
print("🔄 开始扫描WiFi...")
result = adb.wifi_scan(device_serial)

if not result.success:
    print(f"❌ 扫描失败: {result.error_message}")
    exit(1)

# 解析结果
print("📊 解析扫描结果...")
networks = adb.parse_wifi_scan_results(result.raw_output)

if not networks:
    print("⚠️  未发现WiFi网络")
    print("原始输出:")
    print(result.raw_output)
    exit(0)

# 显示结果
print(f"\n✅ 扫描完成！发现 {len(networks)} 个WiFi网络:\n")
print(f"{'WiFi名称':<20} {'信号强度':<15} {'频段':<8} {'加密方式':<10}")
print("-" * 60)

for net in networks[:10]:  # 只显示前10个
    ssid = net['ssid'][:18]  # 截断过长的SSID
    signal = f"{net['signal']}dBm ({net['signal_level']})"
    band = net['band']
    security = net['security']
    print(f"{ssid:<20} {signal:<15} {band:<8} {security:<10}")

print("\n✨ 测试完成！")
```

运行测试：
```powershell
python test_wifi_scan.py
```

---

### 测试4：GUI功能测试

```powershell
# 启动程序
python main.py
```

**测试步骤**：
1. ✅ 程序正常启动
2. ✅ 菜单栏显示"🔍 扫描并连接WiFi"选项
3. ✅ 点击菜单打开扫描对话框
4. ✅ 点击"扫描WiFi"按钮
5. ✅ 等待3秒后显示WiFi列表
6. ✅ WiFi列表包含：名称、信号、频段、加密方式
7. ✅ 双击WiFi可以选择
8. ✅ 输入密码后可以连接
9. ✅ 原有"激活盒子WiFi链接"功能仍然可用

---

## 测试清单

### 基础功能测试

- [ ] 配置文件包含扫描命令
- [ ] ADB命令可以手动执行
- [ ] Python扫描方法正常工作
- [ ] 扫描结果可以正确解析
- [ ] GUI菜单显示正常
- [ ] 扫描对话框可以打开
- [ ] 扫描功能可以执行
- [ ] WiFi列表可以显示
- [ ] WiFi可以选择
- [ ] 连接功能正常

### 边界条件测试

- [ ] 无设备时的提示
- [ ] 多设备时的选择
- [ ] 扫描无结果时的处理
- [ ] 扫描失败时的错误提示
- [ ] 无密码WiFi的连接
- [ ] 错误密码的处理
- [ ] 信号弱WiFi的连接

### 兼容性测试

- [ ] 原有手动输入功能正常
- [ ] WiFi历史记录功能正常
- [ ] 网络测试功能正常
- [ ] 日志记录功能正常

---

## 预期结果

### 成功场景

```
✅ 使用设备: AC8267001234
🔄 开始扫描WiFi...
📊 解析扫描结果...

✅ 扫描完成！发现 6 个WiFi网络:

WiFi名称              信号强度         频段     加密方式  
------------------------------------------------------------
ATC_SD5_5G           -35dBm (优秀)   5G       WPA2      
OfficeWiFi           -48dBm (优秀)   2.4G     WPA2      
HomeWiFi_5G          -58dBm (良好)   5G       WPA3      
GuestNetwork         -72dBm (一般)   2.4G     WPA2      
CafeWiFi             -78dBm (一般)   2.4G     Open      
PublicWiFi           -85dBm (差)     2.4G     Open      

✨ 测试完成！
```

### 失败场景处理

```
❌ 扫描失败: WiFi扫描启动失败
或
⚠️  未发现WiFi网络
原始输出:
[显示原始ADB输出]
```

---

## 问题记录

如果测试中发现问题，请记录：

1. **问题描述**:
2. **复现步骤**:
3. **设备信息**:
4. **日志输出**:
5. **预期行为**:
6. **实际行为**:

---

## 测试报告模板

```
WiFi扫描功能测试报告
====================

测试日期: 2025-01-XX
测试人员: [姓名]
设备型号: [设备型号]
Android版本: [版本号]

测试结果:
✅ 配置文件正常
✅ ADB命令正常
✅ Python功能正常
✅ GUI功能正常
✅ 连接功能正常

发现的问题:
1. [描述问题]
2. [描述问题]

建议:
1. [改进建议]
2. [改进建议]

总体评价: [通过/需要修复]
```
