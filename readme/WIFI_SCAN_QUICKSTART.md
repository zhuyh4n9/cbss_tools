# WiFi 扫描功能 - 快速实现指南

## 🚀 快速开始（3步实现）

### 步骤 1：添加ADB命令配置

在 `config/default_config.ini` 的 `[ADB_Commands]` 节添加：

```ini
wifi_start_scan = shell cmd wifi start-scan
wifi_list_scan_results = shell cmd wifi list-scan-results
```

---

### 步骤 2：在 adb_manager.py 添加扫描方法

复制以下代码到 `adb_manager.py` 的WiFi操作区域：

```python
def wifi_scan(self, serial: str) -> CommandResult:
    """扫描WiFi热点"""
    # 确保WiFi已开启
    self.wifi_enable(serial)
    
    # 启动扫描
    scan_command = self.config.get_adb_command('wifi_start_scan')
    self.execute_adb_command(scan_command, serial)
    
    # 等待扫描完成
    import time
    time.sleep(3)
    
    # 获取扫描结果
    results_command = self.config.get_adb_command('wifi_list_scan_results')
    return self.execute_adb_command(results_command, serial)

def parse_wifi_scan_results(self, raw_output: str) -> List[Dict[str, str]]:
    """解析WiFi扫描结果"""
    networks = []
    lines = raw_output.strip().split('\n')
    
    for line in lines[1:]:  # 跳过标题行
        parts = line.split()
        if len(parts) < 4:
            continue
        
        ssid = parts[0]
        signal = parts[3]
        
        # 判断加密方式
        capabilities = ' '.join(parts[4:]) if len(parts) > 4 else ''
        if "WPA3" in capabilities:
            security = "wpa3"
        elif "WPA2" in capabilities or "WPA" in capabilities:
            security = "wpa2"
        else:
            security = "open"
        
        networks.append({
            'ssid': ssid,
            'signal': signal,
            'security': security
        })
    
    return networks
```

---

### 步骤 3：测试扫描功能

#### 方法 A：命令行测试

```python
# 在Python控制台测试
from src.config_manager import ConfigManager
from src.adb_manager import ADBManager

config = ConfigManager()
adb = ADBManager(config)

# 获取设备
devices = adb.get_connected_devices()
device_serial = devices[0].serial

# 执行扫描
result = adb.wifi_scan(device_serial)
print(result.raw_output)

# 解析结果
networks = adb.parse_wifi_scan_results(result.raw_output)
for net in networks:
    print(f"{net['ssid']}: {net['signal']}dBm, {net['security']}")
```

#### 方法 B：GUI测试

在 `main_gui.py` 的工具菜单添加测试按钮：

```python
# 在 create_menu_bar() 中添加
tools_menu.add_command(label="🔍 测试WiFi扫描", command=self.test_wifi_scan)

def test_wifi_scan(self):
    """测试WiFi扫描功能"""
    authenticators = list(self.device_monitor.authenticators.keys())
    if not authenticators:
        messagebox.showerror("错误", "未检测到设备")
        return
    
    device_serial = authenticators[0]
    
    # 执行扫描
    result = self.adb_manager.wifi_scan(device_serial)
    
    if result.success:
        # 解析结果
        networks = self.adb_manager.parse_wifi_scan_results(result.raw_output)
        
        # 显示结果
        msg = f"扫描完成！发现 {len(networks)} 个WiFi网络：\n\n"
        for net in networks[:10]:  # 只显示前10个
            msg += f"• {net['ssid']}: {net['signal']}dBm ({net['security']})\n"
        
        messagebox.showinfo("扫描结果", msg)
    else:
        messagebox.showerror("扫描失败", result.error_message)
```

---

## 📱 手动测试命令

### 在终端中测试ADB命令：

```powershell
# 1. 列出设备
adb devices

# 2. 开启WiFi
adb -s <device_serial> shell cmd wifi set-wifi-enabled enabled

# 3. 启动扫描
adb -s <device_serial> shell cmd wifi start-scan

# 4. 等待3秒
Start-Sleep -Seconds 3

# 5. 查看结果
adb -s <device_serial> shell cmd wifi list-scan-results
```

### 预期输出：

```
SSID            BSSID             Frequency  Signal  Capabilities
OfficeWiFi      aa:bb:cc:dd:ee:ff 2437       -45     [WPA2-PSK-CCMP][ESS]
HomeWiFi        11:22:33:44:55:66 5180       -52     [WPA3-PSK-CCMP][ESS]
GuestNetwork    77:88:99:aa:bb:cc 2462       -68     [WPA-PSK-CCMP][ESS]
```

---

## 🎨 简化版扫描对话框

如果只需要基本功能，可以使用简化版：

```python
import tkinter as tk
from tkinter import ttk, messagebox
import threading

class SimpleWifiScanDialog:
    """简化版WiFi扫描对话框"""
    def __init__(self, parent, device_serial, adb_manager, callback):
        self.device_serial = device_serial
        self.adb_manager = adb_manager
        self.callback = callback
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("WiFi扫描")
        self.dialog.geometry("500x400")
        
        # 扫描按钮
        ttk.Button(self.dialog, text="扫描WiFi", 
                  command=self.scan).pack(pady=10)
        
        # WiFi列表
        self.listbox = tk.Listbox(self.dialog, height=15)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=10)
        
        # 密码输入
        pwd_frame = ttk.Frame(self.dialog)
        pwd_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(pwd_frame, text="密码:").pack(side=tk.LEFT)
        self.pwd_entry = ttk.Entry(pwd_frame, show='*')
        self.pwd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # 连接按钮
        ttk.Button(self.dialog, text="连接", 
                  command=self.connect).pack(pady=5)
        
        self.networks = []
    
    def scan(self):
        """扫描WiFi"""
        def worker():
            result = self.adb_manager.wifi_scan(self.device_serial)
            if result.success:
                self.networks = self.adb_manager.parse_wifi_scan_results(
                    result.raw_output
                )
                self.dialog.after(0, self.update_list)
            else:
                self.dialog.after(0, lambda: messagebox.showerror(
                    "错误", f"扫描失败: {result.error_message}"
                ))
        
        threading.Thread(target=worker, daemon=True).start()
    
    def update_list(self):
        """更新列表"""
        self.listbox.delete(0, tk.END)
        for net in self.networks:
            text = f"{net['ssid']} ({net['signal']}dBm, {net['security']})"
            self.listbox.insert(tk.END, text)
    
    def connect(self):
        """连接WiFi"""
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请选择WiFi")
            return
        
        network = self.networks[selection[0]]
        password = self.pwd_entry.get()
        
        self.dialog.destroy()
        self.callback(self.device_serial, network['ssid'], 
                     password, network['security'])

# 使用方法：
# dialog = SimpleWifiScanDialog(
#     root, device_serial, adb_manager, perform_wifi_connect
# )
```

---

## ⚠️ 常见问题

### Q1: 扫描返回空列表？

**检查清单**：
- [ ] WiFi是否已开启？
- [ ] 是否等待了足够时间（3-5秒）？
- [ ] 设备是否支持该命令？

**调试方法**：
```python
# 打印原始输出
result = adb.wifi_scan(device_serial)
print(f"Success: {result.success}")
print(f"Raw output:\n{result.raw_output}")
```

### Q2: 解析失败？

**可能原因**：不同Android版本输出格式不同

**解决方案**：添加更灵活的解析逻辑
```python
# 尝试多种分隔符
if '\t' in line:
    parts = line.split('\t')
elif '  ' in line:  # 多个空格
    parts = [p for p in line.split(' ') if p]
```

### Q3: 中文SSID乱码？

**解决方案**：
```python
# 在 execute_adb_command 中设置编码
result = subprocess.run(
    full_command,
    capture_output=True,
    text=True,
    encoding='utf-8',  # 指定UTF-8编码
    timeout=240
)
```

---

## 🔗 下一步

1. ✅ 实现基本扫描功能（当前文档）
2. ⬜ 添加完整的图形界面
3. ⬜ 实现信号强度图标
4. ⬜ 添加自动刷新功能
5. ⬜ 支持保存多个WiFi配置

完整实现请参考：[WIFI_SCAN_ANALYSIS.md](./WIFI_SCAN_ANALYSIS.md)

---

## 📞 获取帮助

- 查看详细文档：`readme/WIFI_SCAN_ANALYSIS.md`
- 测试ADB命令：使用上面的PowerShell命令
- 检查日志：`logs/cbss_tool.log`
