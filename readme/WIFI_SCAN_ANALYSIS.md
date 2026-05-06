# WiFi 热点扫描功能分析与实现方案

## 📋 需求分析

在认证盒子（激活盒子）中实现WiFi热点扫描功能，让用户可以：
1. 查看设备周围可用的WiFi网络列表
2. 显示WiFi信号强度、加密方式等信息
3. 选择扫描到的WiFi进行连接（无需手动输入SSID）

---

## 🔍 技术调研

### Android WiFi 扫描命令

Android 系统提供了多种方式扫描WiFi热点：

#### 方法 1：使用 `cmd wifi` 命令（推荐）

```bash
# 开启WiFi（如果未开启）
adb shell cmd wifi set-wifi-enabled enabled

# 启动WiFi扫描
adb shell cmd wifi start-scan

# 等待扫描完成（通常需要2-5秒）
sleep 3

# 获取扫描结果
adb shell cmd wifi list-scan-results
```

**输出示例**：
```
SSID            BSSID             Frequency  Signal  Capabilities
OfficeWiFi      aa:bb:cc:dd:ee:ff 2437       -45     [WPA2-PSK-CCMP][ESS]
HomeWiFi_5G     11:22:33:44:55:66 5180       -52     [WPA3-PSK-CCMP][ESS]
GuestNetwork    77:88:99:aa:bb:cc 2462       -68     [WPA-PSK-CCMP][WPS][ESS]
OpenWiFi        dd:ee:ff:00:11:22 2412       -75     [ESS]
```

**字段说明**：
- **SSID**: WiFi网络名称
- **BSSID**: 设备MAC地址
- **Frequency**: 工作频率（MHz）
  - 2400-2500: 2.4GHz
  - 5000-6000: 5GHz
- **Signal**: 信号强度（dBm）
  - -30 ~ -50: 优秀
  - -50 ~ -70: 良好
  - -70 ~ -85: 一般
  - < -85: 差
- **Capabilities**: 加密方式和特性
  - WPA2-PSK: WPA2加密
  - WPA3-PSK: WPA3加密
  - ESS: 基础设施模式

#### 方法 2：使用 `wpa_cli` 命令

```bash
# 扫描
adb shell wpa_cli scan

# 获取结果
adb shell wpa_cli scan_results
```

**输出示例**：
```
bssid / frequency / signal level / flags / ssid
aa:bb:cc:dd:ee:ff   2437    -45     [WPA2-PSK-CCMP][ESS]    OfficeWiFi
11:22:33:44:55:66   5180    -52     [WPA3-PSK-CCMP][ESS]    HomeWiFi_5G
```

#### 方法 3：读取系统文件（备用）

```bash
# 查看已保存的网络
adb shell dumpsys wifi
```

---

## 💡 实现方案

### 方案设计

```
用户点击"扫描WiFi热点"
    ↓
开启设备WiFi（如果未开启）
    ↓
执行扫描命令
    ↓
等待2-5秒（扫描过程）
    ↓
获取扫描结果
    ↓
解析结果（SSID、信号强度、加密方式）
    ↓
在对话框中显示可用WiFi列表
    ↓
用户选择WiFi并输入密码
    ↓
执行连接操作
```

---

## 🛠️ 代码实现

### 1. 在 `config/default_config.ini` 添加命令

```ini
[ADB_Commands]
# ...existing commands...
wifi_start_scan = shell cmd wifi start-scan
wifi_list_scan_results = shell cmd wifi list-scan-results
```

### 2. 在 `adb_manager.py` 添加扫描方法

```python
# ------------------ WiFi 扫描操作 ------------------
def wifi_scan(self, serial: str) -> CommandResult:
    """扫描WiFi热点"""
    # 确保WiFi已开启
    enable_result = self.wifi_enable(serial)
    if not enable_result.success:
        return CommandResult(
            success=False,
            status_code=1,
            error_message="无法开启WiFi"
        )
    
    # 启动扫描
    scan_command = self.config.get_adb_command('wifi_start_scan')
    scan_result = self.execute_adb_command(scan_command, serial)
    
    if not scan_result.success:
        return CommandResult(
            success=False,
            status_code=1,
            error_message="WiFi扫描启动失败"
        )
    
    # 等待扫描完成
    import time
    time.sleep(3)  # 等待3秒让扫描完成
    
    # 获取扫描结果
    results_command = self.config.get_adb_command('wifi_list_scan_results')
    results = self.execute_adb_command(results_command, serial)
    
    return results

def parse_wifi_scan_results(self, raw_output: str) -> List[Dict[str, str]]:
    """
    解析WiFi扫描结果
    
    Returns:
        List of wifi networks with keys:
        - ssid: WiFi名称
        - bssid: MAC地址
        - frequency: 频率
        - signal: 信号强度
        - security: 加密方式
        - band: 频段 (2.4G/5G)
        - signal_level: 信号等级 (优秀/良好/一般/差)
    """
    networks = []
    lines = raw_output.strip().split('\n')
    
    # 跳过标题行
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        
        # 解析行: SSID BSSID Frequency Signal Capabilities
        parts = line.split()
        if len(parts) < 5:
            continue
        
        ssid = parts[0]
        bssid = parts[1]
        frequency = parts[2]
        signal = parts[3]
        capabilities = ' '.join(parts[4:])
        
        # 判断频段
        try:
            freq_int = int(frequency)
            if 2400 <= freq_int <= 2500:
                band = "2.4G"
            elif 5000 <= freq_int <= 6000:
                band = "5G"
            else:
                band = "Unknown"
        except ValueError:
            band = "Unknown"
        
        # 判断信号强度等级
        try:
            signal_int = int(signal)
            if signal_int >= -50:
                signal_level = "优秀"
            elif signal_int >= -70:
                signal_level = "良好"
            elif signal_int >= -85:
                signal_level = "一般"
            else:
                signal_level = "差"
        except ValueError:
            signal_level = "未知"
        
        # 判断加密方式
        security = "Open"
        if "WPA3" in capabilities:
            security = "WPA3"
        elif "WPA2" in capabilities:
            security = "WPA2"
        elif "WPA" in capabilities:
            security = "WPA"
        elif "WEP" in capabilities:
            security = "WEP"
        
        networks.append({
            'ssid': ssid,
            'bssid': bssid,
            'frequency': frequency,
            'signal': signal,
            'security': security,
            'band': band,
            'signal_level': signal_level,
            'raw_capabilities': capabilities
        })
    
    # 按信号强度排序（从强到弱）
    networks.sort(key=lambda x: int(x['signal']), reverse=True)
    
    return networks
```

### 3. 创建WiFi扫描对话框

```python
class WifiScanDialog:
    """WiFi扫描和连接对话框"""
    def __init__(self, parent, device_serial: str, adb_manager, callback, config_manager=None):
        self.device_serial = device_serial
        self.adb_manager = adb_manager
        self.callback = callback
        self.config_manager = config_manager
        self.networks = []
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"WiFi热点扫描 - {device_serial}")
        self.dialog.geometry("700x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 顶部按钮区域
        top_frame = ttk.Frame(self.dialog)
        top_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(top_frame, text="🔄 扫描WiFi", command=self.start_scan).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="刷新", command=self.refresh_list).pack(side=tk.LEFT, padx=5)
        
        self.scan_status_label = ttk.Label(top_frame, text="点击'扫描WiFi'开始", foreground="gray")
        self.scan_status_label.pack(side=tk.LEFT, padx=20)
        
        # WiFi列表区域
        list_frame = ttk.LabelFrame(self.dialog, text="可用WiFi网络", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # 创建表格
        columns = ('SSID', '信号', '频段', '加密', 'BSSID')
        self.wifi_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        
        # 设置列标题和宽度
        self.wifi_tree.heading('SSID', text='WiFi名称')
        self.wifi_tree.heading('信号', text='信号强度')
        self.wifi_tree.heading('频段', text='频段')
        self.wifi_tree.heading('加密', text='加密方式')
        self.wifi_tree.heading('BSSID', text='MAC地址')
        
        self.wifi_tree.column('SSID', width=180, anchor='w')
        self.wifi_tree.column('信号', width=100, anchor='center')
        self.wifi_tree.column('频段', width=80, anchor='center')
        self.wifi_tree.column('加密', width=80, anchor='center')
        self.wifi_tree.column('BSSID', width=140, anchor='center')
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.wifi_tree.yview)
        self.wifi_tree.configure(yscrollcommand=scrollbar.set)
        
        self.wifi_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 双击事件
        self.wifi_tree.bind('<Double-1>', self.on_wifi_selected)
        
        # 密码输入区域
        pwd_frame = ttk.Frame(self.dialog)
        pwd_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Label(pwd_frame, text="密码:").pack(side=tk.LEFT)
        self.pwd_var = tk.StringVar()
        # 加载历史密码
        if self.config_manager:
            history = self.config_manager.get_wifi_history()
            self.pwd_var.set(history.get('password', ''))
        
        ttk.Entry(pwd_frame, textvariable=self.pwd_var, show='*', width=40).pack(side=tk.LEFT, padx=10)
        
        # 底部按钮
        bottom_frame = ttk.Frame(self.dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(bottom_frame, text="连接选中WiFi", command=self.connect_wifi).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="关闭", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
    def start_scan(self):
        """开始WiFi扫描"""
        self.scan_status_label.config(text="正在扫描...", foreground="blue")
        self.dialog.update()
        
        def scan_worker():
            try:
                # 执行扫描
                result = self.adb_manager.wifi_scan(self.device_serial)
                
                if result.success:
                    # 解析结果
                    self.networks = self.adb_manager.parse_wifi_scan_results(result.raw_output)
                    self.dialog.after(0, self.display_results)
                else:
                    self.dialog.after(0, lambda: self.scan_error(result.error_message))
            except Exception as e:
                self.dialog.after(0, lambda: self.scan_error(str(e)))
        
        threading.Thread(target=scan_worker, daemon=True).start()
    
    def display_results(self):
        """显示扫描结果"""
        # 清空现有列表
        for item in self.wifi_tree.get_children():
            self.wifi_tree.delete(item)
        
        # 添加新结果
        for network in self.networks:
            signal_display = f"{network['signal']}dBm ({network['signal_level']})"
            self.wifi_tree.insert('', 'end', values=(
                network['ssid'],
                signal_display,
                network['band'],
                network['security'],
                network['bssid']
            ))
        
        count = len(self.networks)
        self.scan_status_label.config(
            text=f"扫描完成，发现 {count} 个WiFi网络",
            foreground="green"
        )
    
    def scan_error(self, error_msg: str):
        """扫描错误处理"""
        self.scan_status_label.config(text=f"扫描失败: {error_msg}", foreground="red")
        messagebox.showerror("扫描失败", f"WiFi扫描失败: {error_msg}")
    
    def refresh_list(self):
        """刷新列表"""
        self.start_scan()
    
    def on_wifi_selected(self, event):
        """WiFi双击事件"""
        self.connect_wifi()
    
    def connect_wifi(self):
        """连接选中的WiFi"""
        selection = self.wifi_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选择要连接的WiFi网络")
            return
        
        # 获取选中的网络
        item = self.wifi_tree.item(selection[0])
        ssid = item['values'][0]
        
        # 找到对应的网络信息
        network = next((n for n in self.networks if n['ssid'] == ssid), None)
        if not network:
            messagebox.showerror("错误", "无法找到选中的网络信息")
            return
        
        # 判断是否需要密码
        password = self.pwd_var.get().strip()
        security = network['security']
        
        if security != "Open" and not password:
            messagebox.showwarning("提示", "此WiFi需要密码，请输入密码")
            return
        
        # 保存历史记录
        if self.config_manager and password:
            self.config_manager.save_wifi_history(ssid, password, 'wpa2' if 'WPA2' in security else 'wpa3')
        
        # 关闭对话框并执行连接
        self.dialog.destroy()
        
        # 根据加密方式选择安全类型
        sec_type = 'wpa2'
        if 'WPA3' in security:
            sec_type = 'wpa3'
        
        self.callback(self.device_serial, ssid, password, sec_type)
```

### 4. 在主GUI中添加菜单项

```python
# 在 create_menu_bar() 方法中添加
tools_menu.add_command(label="扫描并连接WiFi", command=self.scan_and_connect_wifi)
```

### 5. 实现扫描入口方法

```python
def scan_and_connect_wifi(self):
    """扫描并连接WiFi"""
    if self.is_operation_in_progress:
        messagebox.showwarning("警告", "正在执行其他操作，请稍后重试")
        return
    
    # 获取激活盒子列表
    authenticators = list(self.device_monitor.authenticators.keys())
    if not authenticators:
        messagebox.showerror("错误", "未检测到激活盒子")
        return
    
    # 如果只有一个设备，直接打开扫描对话框
    if len(authenticators) == 1:
        device_serial = authenticators[0]
        dialog = WifiScanDialog(
            self.root,
            device_serial,
            self.adb_manager,
            self.perform_authenticator_wifi_connect,
            self.config_manager
        )
        return
    
    # 多个设备时，先让用户选择
    # 这里可以创建一个设备选择对话框，或者使用简单的输入框
    from tkinter import simpledialog
    device_serial = simpledialog.askstring(
        "选择设备",
        f"请输入设备序列号（可用设备：{', '.join(authenticators)}）:"
    )
    
    if device_serial and device_serial in authenticators:
        dialog = WifiScanDialog(
            self.root,
            device_serial,
            self.adb_manager,
            self.perform_authenticator_wifi_connect,
            self.config_manager
        )
    elif device_serial:
        messagebox.showerror("错误", f"设备 {device_serial} 不在可用列表中")
```

---

## 📊 界面效果预览

```
┌─────────────────────────────────────────────────────────────┐
│  WiFi热点扫描 - AC8267001234                        [ X ]   │
├─────────────────────────────────────────────────────────────┤
│  [🔄 扫描WiFi]  [刷新]    扫描完成，发现 8 个WiFi网络        │
├─────────────────────────────────────────────────────────────┤
│  可用WiFi网络                                               │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ WiFi名称      │ 信号强度      │ 频段 │ 加密 │ MAC地址  │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │ OfficeWiFi    │ -42dBm (优秀) │ 5G   │ WPA2 │ aa:bb:cc │ │
│  │ OfficeWiFi    │ -48dBm (优秀) │ 2.4G │ WPA2 │ aa:bb:dd │ │
│  │ HomeWiFi_5G   │ -55dBm (良好) │ 5G   │ WPA3 │ 11:22:33 │ │
│  │ GuestNetwork  │ -68dBm (良好) │ 2.4G │ WPA2 │ 77:88:99 │ │
│  │ CafeWiFi      │ -72dBm (一般) │ 2.4G │ WPA2 │ 44:55:66 │ │
│  │ OpenWiFi      │ -78dBm (一般) │ 2.4G │ Open │ dd:ee:ff │ │
│  │ ...                                                     │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  密码: [******************]                                │
│                                                             │
│  [连接选中WiFi]                              [关闭]        │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ 功能特点

1. **自动扫描**：一键扫描周围所有WiFi热点
2. **信息详细**：显示信号强度、频段、加密方式等
3. **智能排序**：按信号强度从强到弱排序
4. **双击连接**：双击WiFi即可选择并连接
5. **历史密码**：自动填充上次使用的密码
6. **开放网络**：自动识别无需密码的开放WiFi
7. **信号分级**：直观显示信号强度等级（优秀/良好/一般/差）
8. **频段识别**：区分2.4G和5G WiFi

---

## 🔒 安全考虑

1. **扫描权限**：需要设备已启用WiFi功能
2. **密码存储**：密码会保存到配置文件（参考WiFi历史记录功能）
3. **开放WiFi**：连接开放WiFi时会提示安全风险（可选）

---

## 🧪 测试步骤

1. **连接设备**：确保激活盒子通过ADB连接
2. **打开扫描**：工具 → 扫描并连接WiFi
3. **执行扫描**：点击"扫描WiFi"按钮
4. **等待结果**：3-5秒后显示WiFi列表
5. **选择WiFi**：双击或选中后输入密码
6. **测试连接**：验证是否成功连接

---

## 🐛 可能遇到的问题

### 问题 1：扫描返回空列表

**原因**：
- WiFi未开启
- 等待时间不足
- 命令不支持

**解决**：
- 确保先执行 `wifi_enable`
- 增加等待时间到5秒
- 检查设备Android版本

### 问题 2：无法解析扫描结果

**原因**：
- 输出格式不同
- 设备使用不同的WiFi命令

**解决**：
- 添加日志输出原始结果
- 适配不同格式的解析
- 使用备用命令（wpa_cli）

### 问题 3：显示乱码或中文SSID问题

**原因**：
- 编码问题

**解决**：
```python
# 在解析时处理编码
ssid = parts[0].encode('latin1').decode('utf-8', errors='ignore')
```

---

## 📝 后续优化

1. **自动刷新**：定时自动刷新WiFi列表
2. **信号图标**：使用图标显示信号强度
3. **已连接标识**：标记当前已连接的WiFi
4. **快速连接**：记住多个常用WiFi配置
5. **WPS连接**：支持WPS一键连接
6. **隐藏网络**：支持连接隐藏SSID的网络

---

## 📚 相关文档

- Android WiFi API: https://developer.android.com/reference/android/net/wifi/package-summary
- ADB Shell Commands: https://adbshell.com/
- WiFi Security Standards: WPA/WPA2/WPA3
