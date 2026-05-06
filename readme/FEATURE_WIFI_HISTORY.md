# 功能更新：WiFi 历史记录

## 功能描述 (Feature Description)

实现了WiFi连接配置的历史记录功能，自动保存和恢复上次使用的WiFi名称、密码和加密方式，提升用户体验。

---

## 功能特性 (Features)

### 1️⃣ 自动保存

当用户成功输入WiFi配置并点击"连接"时，系统会自动保存以下信息：
- **SSID**：WiFi网络名称
- **密码**：WiFi密码（明文保存在配置文件中）
- **加密方式**：wpa2 或 wpa3

### 2️⃣ 自动恢复

下次打开WiFi配置对话框时，输入框会自动填充上次使用的配置：
- SSID输入框显示上次的网络名称
- 密码输入框显示上次的密码（虽然是`*`显示，但值已填充）
- 加密方式下拉框选中上次的加密类型

### 3️⃣ 手动修改

用户可以随时修改任何字段，新的配置会在点击"连接"后自动覆盖旧的历史记录。

---

## 实现细节 (Implementation Details)

### 1. 配置文件更新

在 `config/default_config.ini` 中添加了新的配置节：

```ini
[WiFi_History]
last_ssid = 
last_password = 
last_security = wpa2
```

**字段说明**：
- `last_ssid`：上次连接的WiFi名称（默认为空）
- `last_password`：上次使用的WiFi密码（默认为空）
- `last_security`：上次使用的加密方式（默认为 wpa2）

### 2. ConfigManager 新增方法

#### `save_wifi_history(ssid, password, security)`
保存WiFi历史记录到配置文件。

```python
def save_wifi_history(self, ssid: str, password: str, security: str):
    """保存WiFi历史记录"""
    if not self.config.has_section('WiFi_History'):
        self.config.add_section('WiFi_History')
    
    self.config.set('WiFi_History', 'last_ssid', ssid)
    self.config.set('WiFi_History', 'last_password', password)
    self.config.set('WiFi_History', 'last_security', security)
    
    # 自动保存到文件
    self.save_config()
    logging.info(f"WiFi历史记录已保存: SSID={ssid}, Security={security}")
```

**特点**：
- 自动创建 `WiFi_History` 配置节（如果不存在）
- 立即保存到磁盘（调用 `save_config()`）
- 记录日志便于调试

#### `get_wifi_history() -> Dict[str, str]`
读取WiFi历史记录。

```python
def get_wifi_history(self) -> Dict[str, str]:
    """获取WiFi历史记录"""
    return {
        'ssid': self.get('WiFi_History', 'last_ssid', ''),
        'password': self.get('WiFi_History', 'last_password', ''),
        'security': self.get('WiFi_History', 'last_security', 'wpa2')
    }
```

**返回格式**：
```python
{
    'ssid': 'MyWiFi',
    'password': 'MyPassword123',
    'security': 'wpa2'
}
```

### 3. WifiConfigDialog 更新

#### 构造函数修改

添加了 `config_manager` 参数，用于访问配置管理器：

```python
def __init__(self, parent, devices: List[str], callback, config_manager=None):
    self.callback = callback
    self.config_manager = config_manager
    
    # ...dialog setup...
    
    # 🆕 加载历史记录
    wifi_history = {'ssid': '', 'password': '', 'security': 'wpa2'}
    if self.config_manager:
        wifi_history = self.config_manager.get_wifi_history()
    
    # 🆕 使用历史记录初始化输入框
    self.ssid_var = tk.StringVar(value=wifi_history['ssid'])
    self.pwd_var = tk.StringVar(value=wifi_history['password'])
    self.sec_var = tk.StringVar(value=wifi_history['security'])
```

#### apply() 方法更新

在用户点击"连接"时保存历史记录：

```python
def apply(self):
    dev = self.dev_var.get()
    ssid = self.ssid_var.get().strip()
    pwd = self.pwd_var.get()
    sec = self.sec_var.get().strip().lower() or 'wpa2'
    
    # ...validation...
    
    # 🆕 保存WiFi历史记录
    if self.config_manager:
        self.config_manager.save_wifi_history(ssid, pwd, sec)
    
    self.dialog.destroy()
    self.callback(dev, ssid, pwd, sec)
```

### 4. 主界面调用更新

在 `authenticator_wifi_connect()` 方法中传入 `config_manager`：

```python
def authenticator_wifi_connect(self):
    # ...checks...
    
    dialog = WifiConfigDialog(
        self.root, 
        authenticators, 
        self.perform_authenticator_wifi_connect, 
        self.config_manager  # 🆕 传入配置管理器
    )
    self.root.wait_window(dialog.dialog)
```

---

## 使用示例 (Usage Examples)

### 场景 1：首次使用

1. 用户点击菜单 **工具 → 激活盒子WiFi链接**
2. 弹出WiFi配置对话框
3. 所有输入框为空（除了加密方式默认为 wpa2）
4. 用户输入：
   - SSID: `OfficeWiFi`
   - 密码: `SecurePass123`
   - 加密方式: `wpa2`
5. 点击"连接"
6. 系统保存历史记录到 `config/default_config.ini`

**配置文件内容**：
```ini
[WiFi_History]
last_ssid = OfficeWiFi
last_password = SecurePass123
last_security = wpa2
```

### 场景 2：第二次使用

1. 用户再次点击 **工具 → 激活盒子WiFi链接**
2. 弹出WiFi配置对话框
3. **自动填充**：
   - SSID: `OfficeWiFi` ✓
   - 密码: `***************` (实际值为 `SecurePass123`) ✓
   - 加密方式: `wpa2` ✓
4. 用户可以直接点击"连接"，或修改任何字段

### 场景 3：切换到新WiFi

1. 用户打开WiFi配置对话框（已填充上次配置）
2. 修改为新的WiFi：
   - SSID: `HomeWiFi`
   - 密码: `MyHomePass456`
   - 加密方式: `wpa3`
3. 点击"连接"
4. 系统更新历史记录

**配置文件更新**：
```ini
[WiFi_History]
last_ssid = HomeWiFi
last_password = MyHomePass456
last_security = wpa3
```

---

## 安全考虑 (Security Considerations)

### ⚠️ 密码明文存储

**当前实现**：WiFi密码以**明文**形式存储在 `config/default_config.ini` 文件中。

**风险**：
- 配置文件可被其他用户/程序读取
- 不适用于高安全性要求的环境

**缓解措施**（可选的未来改进）：
1. **加密存储**：使用简单的加密算法（如 Base64 + XOR）
2. **操作系统凭据管理**：使用 Windows Credential Manager
3. **提示用户**：在对话框中添加安全提示
4. **可选功能**：允许用户禁用历史记录功能

### 建议的改进示例

```python
import base64

def save_wifi_history(self, ssid: str, password: str, security: str):
    """保存WiFi历史记录（密码简单加密）"""
    # 简单的 Base64 编码（注意：这不是真正的加密！）
    encoded_password = base64.b64encode(password.encode()).decode()
    
    self.config.set('WiFi_History', 'last_ssid', ssid)
    self.config.set('WiFi_History', 'last_password', encoded_password)
    self.config.set('WiFi_History', 'last_security', security)
    self.save_config()

def get_wifi_history(self) -> Dict[str, str]:
    """获取WiFi历史记录（密码解密）"""
    encoded_password = self.get('WiFi_History', 'last_password', '')
    password = ''
    if encoded_password:
        try:
            password = base64.b64decode(encoded_password).decode()
        except:
            password = ''
    
    return {
        'ssid': self.get('WiFi_History', 'last_ssid', ''),
        'password': password,
        'security': self.get('WiFi_History', 'last_security', 'wpa2')
    }
```

---

## 测试验证 (Testing)

### 测试步骤

1. **启动程序**
   ```bash
   python main.py
   ```

2. **首次配置WiFi**
   - 工具 → 激活盒子WiFi链接
   - 输入测试WiFi信息
   - 点击"连接"

3. **验证保存**
   - 查看 `config/default_config.ini`
   - 确认 `[WiFi_History]` 节存在
   - 确认 SSID、密码、加密方式已保存

4. **验证恢复**
   - 关闭对话框
   - 重新打开 WiFi 配置对话框
   - 确认输入框已自动填充

5. **验证更新**
   - 修改配置信息
   - 点击"连接"
   - 确认配置文件已更新

### 预期结果

✅ 历史记录正确保存  
✅ 下次打开自动填充  
✅ 修改后正确更新  
✅ 不影响WiFi连接功能  

---

## 修改文件清单 (Modified Files)

| 文件 | 修改类型 | 说明 |
|------|---------|------|
| `config/default_config.ini` | 新增 | 添加 `[WiFi_History]` 配置节 |
| `src/config_manager.py` | 新增方法 | `save_wifi_history()`, `get_wifi_history()` |
| `src/main_gui.py` | 修改 | `WifiConfigDialog` 构造函数和 `apply()` 方法 |
| `src/main_gui.py` | 修改 | `authenticator_wifi_connect()` 传递 `config_manager` |

---

## 版本信息 (Version)

- **工具版本**: v2.2
- **功能添加日期**: 2025-01-XX
- **功能类型**: 用户体验改进

---

## 后续优化建议 (Future Improvements)

### 1. 多WiFi配置管理

支持保存多个WiFi配置，类似WiFi配置文件列表：

```ini
[WiFi_Profiles]
profile_count = 3

[WiFi_Profile_1]
name = Office WiFi
ssid = OfficeWiFi
password = SecurePass123
security = wpa2

[WiFi_Profile_2]
name = Home WiFi
ssid = HomeWiFi
password = MyHomePass456
security = wpa3
```

在对话框中添加下拉列表选择历史配置。

### 2. 密码加密存储

使用更安全的加密方式存储密码：
- Windows: DPAPI (Data Protection API)
- 跨平台: cryptography 库

### 3. 自动连接选项

添加"记住密码"和"自动连接"复选框：
```python
self.remember_pwd = tk.BooleanVar(value=True)
ttk.Checkbutton(self.dialog, text="记住密码", variable=self.remember_pwd)
```

### 4. 配置导入/导出

允许用户导出WiFi配置到文件，便于在多台电脑间共享。

---

## 相关文档 (Related Documentation)

- [CHECKPOINT_V2.2.md](./CHECKPOINT_V2.2.md) - V2.2 版本检查点
- [UPDATE_4_SUMMARY.md](./UPDATE_4_SUMMARY.md) - Update 4 功能总结
- [BUGFIX_WIFI_PING_DNS.md](./BUGFIX_WIFI_PING_DNS.md) - WiFi DNS 问题修复
