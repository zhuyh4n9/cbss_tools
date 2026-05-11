# cbss_tools 维护 Skill

## 目标
用于指导维护 `cbss_tools` / `cbss_host_tool` 相关 PC 端代码（The Cube）时的分析与改动路径，确保新增能力可落在现有架构中。本文档同时是全量功能清单，便于快速定位。

---

## 一、全量功能清单

### 1. 核心授权流程
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 单设备授权 | `AuthenticatorToolGUI.authenticate_device()` | `src/main_gui.py` |
| 单设备授权执行 | `AuthenticationManager.authenticate_device()` → `_perform_authentication()` | `src/auth_manager.py` |
| 批量设备授权 | `AuthenticatorToolGUI.authenticate_all_devices()` | `src/main_gui.py` |
| 批量授权执行 | `AuthenticationManager.authenticate_all_devices()` | `src/auth_manager.py` |
| 自动授权（后台队列） | `AuthenticationManager.set_auto_activation_enabled(True)` | `src/auth_manager.py` |
| 授权流程（step by step） | `_perform_authentication()`: device_uuid → authenticator_sign → device_activate → state验证 | `src/auth_manager.py` |

### 2. 认证器（Cube）管理
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| Cube 快照刷新 | `CubeManager` 周期轮询 `authenticator_snapshot` | `src/cube_manager.py` |
| 锁定认证器 | `AuthenticatorToolGUI.lock_authenticator()` | `src/main_gui.py` |
| 解锁认证器 | `AuthenticatorToolGUI.unlock_authenticator()` | `src/main_gui.py` |
| 激活认证器 | `AuthenticatorToolGUI.activate_authenticator()` | `src/main_gui.py` |
| 配置认证器 | `AuthenticatorToolGUI.config_authenticator()` | `src/main_gui.py` |
| 认证器通用操作 | `AuthenticatorToolGUI.show_authenticator_operation_dialog()` | `src/main_gui.py` |
| 模拟 Cube 创建 | `AuthenticatorToolGUI.show_create_simulated_cube_dialog()` | `src/main_gui.py` |
| 模拟 Cube 加载 | `AuthenticatorToolGUI.show_load_simulated_cube_dialog()` | `src/main_gui.py` |
| 模拟 Cube 签名（ECDSA P-256+ SHA-256） | `SimulateCube.sign_uuid()` | `src/cube.py` |
| 真实 Cube 签名（ADB） | `RealCube.sign_uuid()` → `ADBManager.authenticator_sign()` | `src/cube.py` / `src/adb_manager.py` |

### 3. 设备发现与分类
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| ADB 设备列表获取 | `ADBManager.get_connected_devices()` | `src/adb_manager.py` |
| 设备监控后台线程 | `DeviceMonitor` 轮询 `get_connected_devices()` | `src/device_monitor.py` |
| 设备分类（authenticator / target） | `DeviceParser` + `DeviceClassificationStrategy` | `src/device_parser.py` / `src/device_classification_strategy.py` |
| 设备重新分类 / 误判修复 | `DeviceParser.sync_connected_devices()` + `_worker_loop()` | `src/device_parser.py` |
| 手动刷新设备 | `AuthenticatorToolGUI.refresh_devices()` | `src/main_gui.py` |
| 模拟设备添加 | `AuthenticatorToolGUI.show_add_simulated_device_dialog()` | `src/main_gui.py` |
| 设备源抽象（ADB / UART） | `DeviceSource` 抽象基类 + `AdbDeviceSource` | `src/device_source.py` |
| 获取设备 UUID | `ADBManager.get_device_uuid()` | `src/adb_manager.py` |
| 获取设备激活状态 | `ADBManager.get_device_state()` | `src/adb_manager.py` |
| 激活目标设备 | `ADBManager.activate_device()` | `src/adb_manager.py` |

### 4. WiFi 管理
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 查看当前 WiFi 状态 | `AuthenticatorToolGUI.view_current_wifi()` | `src/main_gui.py` |
| WiFi 扫描 + 连接 | `AuthenticatorToolGUI.scan_and_connect_wifi()` | `src/main_gui.py` |
| WiFi 直连（SSID手动输入） | `AuthenticatorToolGUI.authenticator_wifi_connect()` | `src/main_gui.py` |
| WiFi 断开 | `AuthenticatorToolGUI.authenticator_wifi_disconnect()` | `src/main_gui.py` |
| 启用 WiFi（Station模式） | `ADBManager.wifi_enable()` | `src/adb_manager.py` |
| 禁用 WiFi | `ADBManager.wifi_disable()` | `src/adb_manager.py` |
| WiFi 连接（wpa2/wpa3/open） | `ADBManager.wifi_connect()` | `src/adb_manager.py` |
| WiFi 热点扫描 | `ADBManager.wifi_scan()` | `src/adb_manager.py` |
| WiFi 状态获取 | `ADBManager.wifi_get_status()` / `get_current_wifi()` | `src/adb_manager.py` |
| WiFi 扫描结果解析（去重/排序） | `ADBManager.parse_wifi_scan_results()` | `src/adb_manager.py` |

### 5. 诊断功能
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| Token 诊断导出 | `AuthenticatorToolGUI.get_token_diagnostic()` | `src/main_gui.py` |
| TA (Trusted Service) 诊断导出 | `AuthenticatorToolGUI.get_trusted_service_diagnostic()` | `src/main_gui.py` |
| 授权记录诊断导出 | `AuthenticatorToolGUI.get_authorization_diagnostic()` | `src/main_gui.py` |
| 诊断日志文件列表 | `ADBManager.list_diagnostic_files()` | `src/adb_manager.py` |
| 文件拉取（adb pull） | `ADBManager.pull_file()` | `src/adb_manager.py` |
| 文件删除 | `ADBManager.remove_file()` | `src/adb_manager.py` |
| 诊断签名验证 | `QuickStressTester.verify_diagnostic_sign()` | `stress_test/quick_stress_test.py` |

### 6. 网络状态监控
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 网络连通性监控（后台线程） | `AuthenticatorToolGUI.start_network_monitoring()` | `src/main_gui.py` |
| 多 Host Ping 测试 | `ADBManager.test_network_connectivity()` | `src/adb_manager.py` |
| 单 Host Ping | `ADBManager.ping_host()` | `src/adb_manager.py` |
| 关键 Host 网关检测 | 基于 `[Network] critical_host` 配置 | `src/main_gui.py` |

### 7. 配置管理
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 加载配置文件 | `ConfigManager` 构造函数 | `src/config_manager.py` |
| 导入配置文件 | `AuthenticatorToolGUI.load_config()` | `src/main_gui.py` |
| 导出配置文件 | `AuthenticatorToolGUI.export_config()` | `src/main_gui.py` |
| 运行时读写配置项 | `ConfigManager.get()` / `getint()` / `getfloat()` / `getboolean()` / `set()` | `src/config_manager.py` |
| ADB 命令模板获取 | `ConfigManager.get_adb_command()` | `src/config_manager.py` |
| 状态码消息获取 | `ConfigManager.get_status_message()` | `src/config_manager.py` |
| WiFi 历史保存/获取 | `ConfigManager.save_last_wifi()` / `get_last_wifi()` | `src/config_manager.py` |

### 8. 日志管理
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 日志初始化（轮转文件+控制台） | `LogManager.setup_logging()` | `src/log_manager.py` |
| 查看日志 | `AuthenticatorToolGUI.view_logs()` | `src/main_gui.py` |
| 调整日志级别 | `AuthenticatorToolGUI.config_log_level()` | `src/main_gui.py` |
| 修改日志文件路径 | `AuthenticatorToolGUI.config_log_path()` | `src/main_gui.py` |
| 获取日志尾部 N 行 | `LogManager.get_log_tail()` | `src/log_manager.py` |
| 清空日志 | `LogManager.clear_log()` | `src/log_manager.py` |
| 运行时改日志级别 | `LogManager.change_log_level()` | `src/log_manager.py` |
| 运行时改日志路径 | `LogManager.change_log_path()` | `src/log_manager.py` |

### 9. UI 国际化（i18n）
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 加载语言提示文件 | `PromptManager` 构造函数 | `src/prompt_manager.py` |
| 获取提示文案 | `PromptManager.get()` | `src/prompt_manager.py` |
| 带格式化的提示文案 | `PromptManager.getf()` | `src/prompt_manager.py` |

### 10. 打包与发布
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 开发环境包 | `PackageBuilder.make_development()` | `package_all.py` |
| 轻量包 | `PackageBuilder.make_lite()` | `package_all.py` |
| 便携 exe 包 | `PackageBuilder.make_portable()` | `package_all.py` |
| 安装器包 | `PackageBuilder.make_installer()` | `package_all.py` |
| 最终发布包 | `PackageBuilder.make_release()` | `package_all.py` |
| 一键全量打包 | `PackageBuilder.make_all()` | `package_all.py` |
| 清理构建产物 | `PackageBuilder.clean()` | `package_all.py` |
| CLI 入口 | `main()` 函数（argparse） | `package_all.py` |

### 11. 压力测试
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 签名压力测试 | `QuickStressTester.test_sign_command()` | `stress_test/quick_stress_test.py` |
| 诊断命令测试 | `QuickStressTester.test_diagnostic_command()` | `stress_test/quick_stress_test.py` |
| 签名验证（ECDSA P-256） | `QuickStressTester.verify_signature()` | `stress_test/quick_stress_test.py` |
| 诊断签名验证 | `QuickStressTester.verify_diagnostic_sign()` | `stress_test/quick_stress_test.py` |

### 12. 其他 UI 功能
| 功能 | 入口方法 | 所在文件 |
|---|---|---|
| 认证器详情弹窗 | `AuthenticatorToolGUI.show_detailed_info()` | `src/main_gui.py` |
| 查看 CHANGELOG | `AuthenticatorToolGUI.show_changelog()` | `src/main_gui.py` |
| 查看帮助 | `AuthenticatorToolGUI.show_help()` | `src/main_gui.py` |
| 关于对话框 | `AuthenticatorToolGUI.show_about()` | `src/main_gui.py` |
| 自动授权开关 | `AuthenticatorToolGUI.toggle_auto_activation()` | `src/main_gui.py` |
| 设备双击激活 | `AuthenticatorToolGUI.on_device_double_click()` | `src/main_gui.py` |
| 设备列表刷新 | `AuthenticatorToolGUI.refresh_devices()` | `src/main_gui.py` |

---

## 二、先理解的数据流（必须）
1. **设备发现**：`DeviceMonitor` 轮询 `adb devices -l`。
2. **设备分类**：`DeviceParser` 将序列号分流为 authenticator / target，维护 `await/ready` 队列。
3. **认证器快照**：`CubeManager` 周期刷新 `snapshot`，并通过回调更新 UI。
4. **授权流程**：`AuthenticationManager._perform_authentication()` 执行
   `device_uuid → authenticator_sign → device_activate → state验证`。

关键文件：
- `src/device_monitor.py` — 设备发现调度中心
- `src/device_parser.py` — 设备分类引擎
- `src/cube_manager.py` — Cube 快照管理
- `src/auth_manager.py` — 授权流程编排（单设备/批量/自动）
- `src/main_gui.py` — Tkinter 主窗口（60+ 公开方法）

---

## 三、cbss_tools 相关改动的标准落点
凡是新增/修改设备能力，按以下顺序改：
1. 在 `config/default_config.ini` 的 `[ADB_Commands]` 新增命令模板。
2. 在 `src/adb_manager.py` 增加同名封装方法（只走 `execute_adb_command()`）。
3. 在 `src/main_gui.py` 或 `src/diaglog/` 接入 UI 入口（菜单/对话框/进度反馈）。
4. 如涉及文案，更新 `config/prompt_chn.ini`，通过 `PromptManager.get()` 取文案。

**禁止**：在 UI 层直接写 `subprocess` 或硬编码 ADB 命令。

---

## 四、输出解析规则（易踩坑）
- 命令成功判定依赖工具输出中的：
  - `[status] <code>[, message]`
  - `[result] <payload>`
- 解析逻辑在 `ADBManager._parse_command_output()`。
- 若 `status_code != 0`，错误文案优先来自 `[status]`，其次回落到 `Status_Messages` 配置。

---

## 五、并发与 UI 更新规则
- 长耗时操作必须放在线程中执行。
- 线程内更新 UI 必须使用 `root.after(...)` 或 `dialog.after(...)` 回主线程。
- 设备分类误判修复依赖 `DeviceParser.sync_connected_devices()` 与 `_worker_loop()` 的重分类逻辑，不要轻易删除重试队列。

---

## 六、联调与回归清单
- 本地运行：`python main.py`
- 打包：`python package_all.py --type release`
- 清理：`python package_all.py --clean`
- 压测/签名验证：`python stress_test/quick_stress_test.py`

回归重点：
1. 认证器不会出现在 target 列表中（尤其 snapshot 瞬时失败时）。
2. 单设备授权与批量授权流程均可闭环。
3. Wi-Fi 连接后 `time_status` / 网络连通性状态更新正常。
4. 日志写入 `logs/cbss_tool.log`，异常可定位。

---

## 七、平台与依赖边界
- **Windows 优先**，ADB 默认路径：`adb/adb.exe`。
- **设备侧依赖**：`cbss_tools`、`cbss_host_tool`（通过 ADB shell 调用）。
- **Python 依赖**：`cryptography`（ECDSA P-256）、`tkinter`。
- **诊断与网络**相关能力依赖 `default_config.ini` 中的命令模板与 `Network` 配置。
- **模拟设备/Cube** 功能受编译选项 `CBSS_ENABLE_SIMULATED_DEVICE` 控制（`src/build_options.py`）。

---

## 八、关键设计决策记录

### 8.1 签名算法
- **算法**：ECDSA with P-256 curve
- **摘要**：SHA-256
- **流程**：对 UUID 明文先计算 SHA-256 哈希，再用私钥对哈希值签名
- **输出格式**：RAW 格式（64字节，r||s），不转 DER
- **关键代码**：`SimulateCube.sign_uuid()`（`src/cube.py`）、`QuickStressTester.verify_signature()`（`stress_test/quick_stress_test.py`）
- **⚠️ 注意**：签名时必须先 hash 再 sign，不可直接对原始 UUID 签名（曾为 bug，已修复）。

### 8.2 设备分类策略
- `DeviceClassificationStrategy` 先查 `list -l` 中的 `product:` 字段。
- 若 product 不可用，回退到 `authenticator_snapshot` 检测。
- 设备分类后进入 `await` 队列等待深度解析，完成后进入 `ready` 队列。

### 8.3 模拟设备/Cube 机制
- 编译期通过环境变量 `CBSS_ENABLE_SIMULATED_DEVICE` 控制。
- 模拟 Cube 使用本地 PEM 私钥 + JSON 持久化。
- 模拟设备维护内存状态，不经过 ADB。

---

## 九、维护建议（针对本项目）
- 做新功能先扩展配置，再扩展 `ADBManager`，最后接 UI。
- 保持 `DeviceMonitor → DeviceParser → CubeManager` 边界清晰，避免把分类与快照逻辑挪回 UI。
- 对外行为变化（菜单、提示、错误）一律走 `prompt_chn.ini`，避免硬编码中文。
- 文件操作全部使用绝对路径或基于项目根路径计算。
- 涉及加密/签名的逻辑变更务必同步更新 `stress_test/quick_stress_test.py` 中的验证代码。