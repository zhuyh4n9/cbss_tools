# 认证器盒子PC Tool - Checkpoint V2.2

**创建时间**: 2025-10-30  
**版本**: 2.2.0  
**状态**: ✅ 生产就绪 + WiFi网络验证和状态监控

## 项目概览

认证器盒子PC Tool是一个基于Python和Tkinter的桌面应用程序，用于管理认证器设备和目标设备的认证流程。V2.2版本在V2.0基础上新增了WiFi连接验证和网络状态实时监控功能。

## 版本更新记录

### V2.2 新增功能 (Update 4)
- ✅ **WiFi连接验证**：连接WiFi后自动进行网络连通性测试
- ✅ **多节点Ping测试**：对多个测试节点进行ping操作，确保网络可用性
- ✅ **可配置测试节点**：支持通过配置文件自定义ping测试节点列表
- ✅ **进度条显示**：WiFi连接和测试过程显示实时进度
- ✅ **时间状态显示**：在认证器状态信息中显示time_status字段
- ✅ **网络状态监控**：后台定期检测网络连通性，不阻塞其他操作
- ✅ **连通性百分比**：实时显示网络连通百分比
- ✅ **关键节点告警**：ntp.ntsc.ac.cn无法ping通时进行提示

### V2.0 新增功能 (Update 1)
- ✅ **设备WiFi连接功能**：工具菜单新增"设备WiFi连接"选项
- ✅ **WiFi配置对话框**：支持SSID、密码、加密方式（wpa2/wpa3）配置
- ✅ **可配置WiFi命令**：支持通过配置文件自定义WiFi相关ADB命令
- ✅ **WiFi操作流程**：支持开启/关闭WiFi station，连接指定网络
- ✅ **引号参数处理**：支持包含空格的SSID和密码

### V1.0 基础功能
- ✅ 完整的设备认证流程
- ✅ 认证器管理（锁定、解锁、激活、配置）
- ✅ 设备监控和状态显示
- ✅ 诊断日志导出
- ✅ 批量认证功能

## 已完成功能清单

### 1. 核心功能模块

#### 1.1 GUI界面 (`src/main_gui.py`)
- ✅ 完整的Tkinter GUI实现
- ✅ 三部分布局：菜单栏、认证器信息面板、设备列表
- ✅ 菜单栏包含：文件、工具、帮助、关于
- ✅ 实时设备监控和状态更新
- ✅ 设备状态颜色编码显示
- ✅ WiFi配置对话框和进度显示
- ✅ **NEW**: 时间状态显示（time_status字段）
- ✅ **NEW**: 网络状态显示（连通百分比）
- ✅ **NEW**: 后台网络监控线程

#### 1.2 ADB通信管理 (`src/adb_manager.py`)
- ✅ 完整的ADB命令执行框架
- ✅ 认证器命令：snapshot, sign, lock, unlock, activate, config
- ✅ 目标设备命令：uuid, state, activate
- ✅ WiFi命令：wifi_enable, wifi_disable, wifi_connect
- ✅ **NEW**: Ping命令：执行网络连通性测试
- ✅ [status] 和 [result] 格式解析
- ✅ 支持每行都有[result]标记的多行格式
- ✅ Unix时间戳自动转换为可读日期格式
- ✅ 使用shlex.split处理引号参数

#### 1.3 配置管理 (`src/config_manager.py`)
- ✅ INI格式配置文件支持
- ✅ 配置加载和导出功能
- ✅ 运行时配置更新
- ✅ 默认配置模板
- ✅ WiFi命令模板配置
- ✅ **NEW**: Ping测试节点配置
- ✅ **NEW**: 网络监控间隔配置

#### 1.4 日志系统 (`src/log_manager.py`)
- ✅ 多级别日志（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- ✅ 日志文件轮转
- ✅ 日志查看器界面
- ✅ 可配置的日志路径和级别

#### 1.5 设备监控 (`src/device_monitor.py`)
- ✅ 后台线程定期扫描设备
- ✅ 设备类型自动识别（认证器/目标设备）
- ✅ 设备连接状态监控
- ✅ 认证器信息解析和缓存
- ✅ 设备状态位解析（锁定、冻结、临时锁定支持）
- ✅ 过期状态检测和颜色编码

#### 1.6 认证管理 (`src/auth_manager.py`)
- ✅ 单设备认证流程
- ✅ 批量设备认证
- ✅ 认证进度显示
- ✅ 认证状态检查

### 2. 网络功能（NEW in V2.2）

#### 2.1 WiFi连接验证
- ✅ 连接WiFi后自动进行网络测试
- ✅ 1秒延迟等待网络稳定
- ✅ 多节点并发ping测试
- ✅ 测试进度实时显示
- ✅ 成功/失败弹框提示

#### 2.2 网络状态监控
- ✅ 后台定期ping测试（默认10秒间隔）
- ✅ 非阻塞式监控，不影响其他操作
- ✅ 连通性百分比计算和显示
- ✅ 关键节点（ntp.ntsc.ac.cn）告警
- ✅ 网络状态颜色编码

#### 2.3 Ping测试配置
默认测试节点列表（可配置）：
- ntp.ntsc.ac.cn（关键节点）
- ntp1.aliyun.com
- www.baidu.com
- www.google.com
- 8.8.8.8
- oss-cn-hangzhou.aliyuncs.com
- obs.cn-north-4.myhuaweicloud.com
- dns.alidns.com
- dns.pub

### 3. 数据解析功能

#### 3.1 命令输出解析
- ✅ [status] 状态码解析
- ✅ [result] 结果数据提取
- ✅ 多行[result]格式支持
- ✅ 逗号分隔字段解析
- ✅ 空格分隔字段解析

#### 3.2 认证器信息解析
- ✅ expired_date: Unix时间戳 → 可读日期
- ✅ counter: 剩余可激活设备数
- ✅ authorized_device_num: 已激活设备数
- ✅ device_status: 状态位解析
  - Bit 0: 锁定状态
  - Bit 1: 冻结状态
  - Bit 2: 临时锁定支持
- ✅ **NEW**: time_status: 时间状态字段

#### 3.3 设备状态解析
- ✅ "Activated" → "Authorized"
- ✅ "Not activated" → "Unauthorized"
- ✅ 状态颜色编码显示

### 4. UI界面功能

#### 4.1 认证器信息显示
- ✅ 下拉选择器
- ✅ 基本信息面板（Serial ID, 设备类型, 最后连接时间）
- ✅ 状态信息面板（过期时间, 剩余设备数, 已激活数, 设备状态）
- ✅ **NEW**: 时间状态显示
- ✅ **NEW**: 网络状态显示（连通百分比）
- ✅ Snapshot数据显示区域
- ✅ 详细信息对话框
- ✅ 状态颜色编码（红色/橙色/绿色）

#### 4.2 设备列表显示
- ✅ 表格视图（序列号, UUID, USB端口, 状态, 操作）
- ✅ 双击认证功能
- ✅ 批量认证按钮
- ✅ 手动刷新按钮

#### 4.3 菜单功能
- ✅ 文件菜单
  - 配置加载
  - 配置导出
  - 配置日志（级别、路径）
  - 查看日志
- ✅ 工具菜单
  - 锁定认证器
  - 解锁认证器
  - 激活认证器
  - 配置认证器
  - 设备WiFi连接（含验证）
  - 设备WiFi断开
  - 诊断日志导出
- ✅ 帮助菜单
  - 使用方法
- ✅ 关于菜单
  - 公司信息、版本信息

### 5. 对话框组件

- ✅ LogLevelDialog: 日志级别配置
- ✅ LogViewDialog: 日志查看器
- ✅ AuthenticatorOperationDialog: 认证器操作对话框
- ✅ AuthenticationDialog: 单设备认证对话框
- ✅ BatchAuthenticationDialog: 批量认证对话框
- ✅ ProgressDialog: 进度显示对话框
- ✅ WifiConfigDialog: WiFi配置对话框
- ✅ WifiDisconnectDialog: WiFi断开对话框
- ✅ DiagnosticDialog: 诊断日志对话框

### 6. 测试文件

- ✅ `test/test_parsing.py`: ADB命令解析测试
- ✅ `test/test_timestamp_parsing.py`: 时间戳转换测试
- ✅ `test/test_device_status.py`: 设备状态解析测试
- ✅ `stress_test/quick_stress_test.py`: 压力测试脚本
- ✅ `demo/demo_ui.py`: UI演示程序

## 项目结构

```
cbss_tool_v2.2/
├── main.py                      # 应用程序入口
├── requirements.txt             # Python依赖
├── README.md                    # 项目说明
├── cbss_simple.spec            # PyInstaller打包配置
├── package_all.py              # 打包脚本
│
├── config/
│   └── default_config.ini      # 默认配置文件
│
├── src/
│   ├── __init__.py
│   ├── main_gui.py             # 主GUI界面（含WiFi验证和网络监控）
│   ├── adb_manager.py          # ADB通信管理（含ping功能）
│   ├── config_manager.py       # 配置管理
│   ├── log_manager.py          # 日志管理
│   ├── device_monitor.py       # 设备监控
│   └── auth_manager.py         # 认证管理
│
├── stress_test/
│   ├── quick_stress_test.py    # 压力测试脚本
│   └── pubkey/
│       └── pub.pem             # 公钥文件
│
├── logs/
│   └── cbss_tool.log           # 日志文件
│
├── adb/
│   ├── adb.exe
│   ├── AdbWinApi.dll
│   └── AdbWinUsbApi.dll
│
├── readme/
│   ├── CHECKPOINT_V1.0.md      # V1.0检查点
│   ├── CHECKPOINT_V2.0.md      # V2.0检查点
│   ├── CHECKPOINT_V2.2.md      # V2.2检查点（本文件）
│   └── PROJECT_STATUS.md       # 项目状态
│
└── require/
    └── require.md              # 需求文档
```

## 配置文件结构

### default_config.ini 主要配置项

```ini
[General]
refresh_rate = 3
adb_path = adb/adb.exe
version = 2.2

[Network]
# 网络监控间隔（秒）
monitor_interval = 10
# Ping测试节点列表（逗号分隔）
ping_hosts = ntp.ntsc.ac.cn,ntp1.aliyun.com,www.baidu.com,www.google.com,8.8.8.8,oss-cn-hangzhou.aliyuncs.com,obs.cn-north-4.myhuaweicloud.com,dns.alidns.com,dns.pub
# 关键节点（无法连通时告警）
critical_host = ntp.ntsc.ac.cn
# Ping超时时间（秒）
ping_timeout = 3
# Ping包数量
ping_count = 1

[UI]
window_title = AC8267激活工具
window_width = 1200
window_height = 800

[ADB_Commands]
# ... 其他命令 ...
ping = shell ping -c {count} -W {timeout} {host}
```

## 技术要点

### 1. 网络连通性测试

#### Ping实现
```python
def ping_host(self, serial: str, host: str, count: int = 1, timeout: int = 3) -> bool:
    """通过adb ping指定主机"""
    command = f"shell ping -c {count} -W {timeout} {host}"
    result = self.execute_adb_command(command, serial)
    # 检查输出中是否包含成功标志
    return "bytes from" in result.raw_output.lower() or "0% packet loss" in result.raw_output.lower()
```

#### 批量测试
```python
def test_network_connectivity(self, serial: str, hosts: List[str]) -> Dict[str, bool]:
    """测试多个主机的连通性"""
    results = {}
    for host in hosts:
        results[host] = self.ping_host(serial, host)
    return results
```

### 2. 后台网络监控

#### 非阻塞监控线程
```python
def start_network_monitoring(self):
    """启动网络监控线程"""
    if hasattr(self, 'network_monitor_thread') and self.network_monitor_thread.is_alive():
        return
    
    self.network_monitor_stop = threading.Event()
    self.network_monitor_thread = threading.Thread(target=self._network_monitor_worker, daemon=True)
    self.network_monitor_thread.start()

def _network_monitor_worker(self):
    """网络监控工作线程"""
    while not self.network_monitor_stop.is_set():
        if self.current_authenticator:
            # 执行ping测试
            results = self.adb_manager.test_network_connectivity(
                self.current_authenticator,
                self.ping_hosts
            )
            # 更新UI显示
            self.root.after(0, lambda: self.update_network_status(results))
        
        # 等待下一次检测
        self.network_monitor_stop.wait(self.monitor_interval)
```

### 3. WiFi连接验证流程

```python
def perform_authenticator_wifi_connect(self, device_serial, ssid, password, security):
    """执行WiFi连接并验证"""
    progress = ProgressDialog(self.root, "设备WiFi连接", "正在准备...")
    
    def worker():
        try:
            # 1. 关闭WiFi
            progress.update_progress("正在关闭WiFi...")
            self.adb_manager.wifi_disable(device_serial)
            
            # 2. 开启WiFi
            progress.update_progress("正在开启WiFi...")
            self.adb_manager.wifi_enable(device_serial)
            
            # 3. 连接WiFi
            progress.update_progress("正在连接WiFi...")
            self.adb_manager.wifi_connect(device_serial, ssid, password, security)
            
            # 4. 等待网络稳定
            progress.update_progress("等待网络稳定...")
            time.sleep(1)
            
            # 5. 测试网络连通性
            progress.update_progress("测试网络连通性...")
            results = self.adb_manager.test_network_connectivity(device_serial, ping_hosts)
            
            # 6. 判断结果
            success_count = sum(1 for v in results.values() if v)
            if success_count == 0:
                raise Exception("所有节点均ping失败，WiFi不可用")
            
            progress.close()
            self.show_success_message(f"WiFi连接成功！连通性: {success_count}/{len(results)}")
            
        except Exception as e:
            progress.close()
            self.show_error_message(f"WiFi连接失败: {e}")
    
    threading.Thread(target=worker, daemon=True).start()
```

## 使用说明

### 1. WiFi连接和验证

1. 选择菜单"工具" → "激活盒子WiFi链接"
2. 在弹出的对话框中：
   - 选择目标设备
   - 输入WiFi SSID
   - 输入WiFi密码
   - 选择加密方式（wpa2/wpa3）
3. 点击"连接"按钮
4. 系统将自动：
   - 连接到指定WiFi
   - 等待1秒让网络稳定
   - 对配置的测试节点进行ping测试
   - 显示测试进度
   - 弹框显示连接结果和连通性统计

### 2. 网络状态监控

- 认证器信息面板中显示"网络状态"
- 实时显示网络连通百分比
- 颜色编码：
  - 绿色：连通性 >= 80%
  - 橙色：50% <= 连通性 < 80%
  - 红色：连通性 < 50%
- 如果关键节点（ntp.ntsc.ac.cn）无法连通，会显示警告图标

### 3. 时间状态显示

- 认证器信息面板中显示"时间状态"
- 从snapshot的time_status字段获取
- 显示设备的时间同步状态

## 配置示例

### 自定义Ping测试节点

编辑`config/default_config.ini`：

```ini
[Network]
# 自定义测试节点
ping_hosts = 192.168.1.1,google.com,baidu.com
# 关键节点
critical_host = 192.168.1.1
# 监控间隔（秒）
monitor_interval = 5
```

### 调整网络监控频率

```ini
[Network]
# 每15秒检测一次
monitor_interval = 15
```

## 依赖项

```
tkinter (Python内置)
python >= 3.6
```

## 已知问题和限制

1. **Ping命令兼容性**：依赖Android设备的ping命令实现
2. **网络监控性能**：大量设备同时监控可能影响性能
3. **WiFi连接超时**：某些设备WiFi连接可能需要更长时间
4. **Ping测试准确性**：单次ping测试可能不够准确

## 未来改进建议

1. **网络诊断**：增加更详细的网络诊断信息（信号强度、IP地址等）
2. **历史记录**：记录网络状态历史，生成图表
3. **智能告警**：网络异常时自动告警
4. **批量WiFi配置**：支持对多个设备批量配置WiFi
5. **WiFi配置模板**：保存常用WiFi配置模板

## 版本历史

- **V2.2.0** (2025-10-30): WiFi验证和网络监控
- **V2.0.0** (2025-10-22): WiFi连接功能
- **V1.0.0** (2025-10-15): 基础功能完成

## 联系方式

- 厂商：Autochips Inc
- 项目：AC8267激活工具

---

**文档生成时间**: 2025-10-30  
**状态**: ✅ 已完成Update 4所有功能
