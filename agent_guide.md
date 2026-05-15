# CBSS Tool Agent  Guide

## 目标
用于指导维护 `cbss_tools` / `cbss_host_tool` 相关 PC 端代码（The Cube）时的分析与改动路径，确保新增能力可落在现有架构中。本文档同时是全量功能清单，便于快速定位。

---

## 全量架构（v3.4.0）

### 数据流
1. **设备探测**：`DeviceMonitor` 通过 `IDeviceDetector` 列表轮询：
   - `AdbDeviceDetector` — ADB 设备（对比上次 serial 列表，上报增删）
   - `SimulatorDeviceDetector` — 模拟设备（用户操作触发 pending 增删事件）
   - Detector 通过 `poll_changes()` 返回 `DeviceChange(added, removed)`，仅上报变化
2. **设备管理**：`DeviceMonitor` 维护 `_connected_index` 统一记录所有探测器上报的设备
   - 仅 `_monitor_loop` 调用 `_update_device_info` 轮询各 Detector 的 `poll_changes()`
   - 仅将增删变化（`added`/`removed`）传递给 `sync_connected_devices`，不刷新全部设备
3. **设备分类**：`DeviceParser` 将序列号分流为 authenticator / target，维护 `await/ready` 队列。
   - `_to_target_device` 会按设备来源创建对象：ADB 设备创建 `UnknownAdbDevice`，模拟设备直接创建 `SimulatorDevice`
   - `DeviceClassificationStrategy.classify_device` 负责后续分类与状态刷新流程
   - 分类完成后在 worker loop 中 `markDirty(kick_trigger)`，仅触发异步刷新；真正的 `refreshDeviceMeta` 在 parser worker 内执行
   - `refreshDeviceMeta` 前后记录 INFO 日志
4. **认证器快照**：`CubeManager` 周期刷新 `snapshot`（仅 Cube，不刷新 target 设备）。
5. **授权流程**：`AuthenticationManager._perform_authentication()` 执行：
   `check state → sign_uuid → log(all/) → double check → activate → log(failure/)`
   - sign_uuid 前必须先确认 device 状态为 Unauthorized，避免消耗 Cube 授权数
   - activate 失败标记 `AuthorizationFailure` 状态，禁止再次授权
   - 失败记录写入 `detailed_info/failure/`，含 Cube status/expire
6. **刷新机制**（仅通过 `markDirty` 触发）：
   - 新增设备 → `markDirty`（worker loop 中）
   - 用户按钮刷新 → 全部设备 `markDirty` + `kick_trigger`
   - 授权完成/失败 → `mark_device_dirty(serial)`
   - `_submitted` 标记防止重复加入自动授权队列

### 关键文件

#### `src/adb_manager.py` — ADB 命令工具
| 类/方法 | 说明 |
|---|---|
| `DeviceInfo` (dataclass) | 设备信息：serial, status, device_type, uuid, usb_port, detection_method, is_simulation |
| `AuthenticatorInfo` (dataclass) | 激活盒子信息：serial, expired_date, counter, authorized_device_num, device_status, time_status, raw_data |
| `CommandResult` (dataclass) | 命令执行结果：success, status_code, result_data, error_message, raw_output |
| `ADBManager.__init__(config_manager)` | 初始化，读取 adb_path 配置 |
| `ADBManager.execute_adb_command(command, serial)` | 执行 ADB 命令（shlex 解析，subprocess 执行，240s 超时） |
| `ADBManager._parse_command_output(output, command_success)` | 解析 `[status]`/`[result]` 行，检测命令错误模式 |
| `ADBManager.get_connected_devices()` | 通过 `adb devices -l` 获取已连接设备列表 |
| `ADBManager.get_device_uuid(serial)` | 获取设备 UUID |
| `ADBManager.get_device_state(serial)` | 获取设备激活状态 |
| `ADBManager.activate_device(serial, signature)` | 激活设备 |
| `ADBManager.get_authenticator_snapshot(serial)` | 获取激活盒子快照 |
| `ADBManager.parse_snapshot_data(raw_output)` | 解析快照数据为 AuthenticatorInfo |
| `ADBManager.authenticator_sign(serial, uuid)` | 激活盒子签名 |
| `ADBManager.authenticator_lock/unlock/activate/config(serial, payload)` | 激活盒子操作 |

#### `src/device_source.py` — 设备探测器
| 类/方法 | 说明 |
|---|---|
| `IDeviceDetector` (ABC) | 探测器抽象基类：get_name(), start(), stop(), poll_devices(), poll_changes() |
| `DeviceChange` (dataclass) | 设备变化：added(List[DeviceInfo]), removed(List[str]) |
| `AdbDeviceDetector.__init__(adb_manager)` | ADB 探测器，维护上次 serial 集合 |
| `AdbDeviceDetector.poll_devices()` | 通过 ADB 获取全量设备列表 |
| `AdbDeviceDetector.poll_changes()` | 对比上次轮询，返回增删变化（首次全部视为新增） |
| `SimulatorDeviceDetector.__init__()` | 模拟探测器，维护设备字典和 pending 增删队列 |
| `SimulatorDeviceDetector.poll_changes()` | 返回并清空 pending 增删事件 |
| `SimulatorDeviceDetector.add_device(status, uuid, serial_number, simulate_activate_failure)` | 创建模拟设备，加入 pending_added |
| `SimulatorDeviceDetector.remove_device(serial)` | 移除模拟设备，加入 pending_removed |
| `SimulatorDeviceDetector.get_device(serial)` | 按 serial 获取 SimulatorDevice |

#### `src/device_monitor.py` — 设备监控管理器
| 类/方法 | 说明 |
|---|---|
| `DeviceMonitor.__init__(adb_manager, config_manager)` | 初始化探测器列表、DeviceParser、回调字典 |
| `DeviceMonitor.start_monitoring()` | 启动探测器 + parser + monitor_loop 线程 |
| `DeviceMonitor.stop_monitoring(join_timeout)` | 停止所有线程 |
| `DeviceMonitor._monitor_loop()` | 主循环：轮询设备变化 + 周期刷新 Cube |
| `DeviceMonitor._update_device_info()` | 遍历探测器 poll_changes()，将增删同步到 parser |
| `DeviceMonitor.register_device_source(source)` | 注册外部探测器 |
| `DeviceMonitor.add_callback/remove_callback(event_type, callback)` | 回调管理 |
| `DeviceMonitor.refresh_devices()` | 手动刷新全部设备（markDirty + kick_trigger） |
| `DeviceMonitor.mark_all_devices_dirty()` | 标记全部设备 dirty |
| `DeviceMonitor.mark_device_dirty(serial)` | 标记单个设备 dirty |
| `DeviceMonitor.reparse_device(serial)` | 激活后重新获取设备状态 |
| `DeviceMonitor.update_device_status(serial, new_status)` | 立即更新设备状态并通知 UI |
| `DeviceMonitor.refresh_all_device()` | 刷新所有设备解析状态 |
| `DeviceMonitor.refresh_all_cube()` | 刷新全部 authenticator 信息 |
| `DeviceMonitor.get_ready_devices()` | 获取已解析完成设备 |
| `DeviceMonitor.get_device_by_serial(serial)` | 按 serial 查找 DeviceInfo |
| `DeviceMonitor.get_authenticator_by_serial(serial)` | 按 serial 查找 AuthenticatorInfo |
| `DeviceMonitor.get_target_device(serial, create_if_missing)` | 获取 ITargetDevice（统一处理真实/模拟） |
| `DeviceMonitor.get_device_auth_status(serial)` | 获取设备认证状态 |
| `DeviceMonitor.add_simulated_device(status, ...)` | 创建模拟设备 |
| `DeviceMonitor.remove_simulated_device(serial)` | 移除模拟设备 |
| `DeviceMonitor.create_simulated_cube(...)` | 创建模拟 Cube |
| `DeviceMonitor.load_simulated_cube(persist_path, private_key_path)` | 加载模拟 Cube |
| `DeviceMonitor.is_simulated_cube(serial)` | 判断是否为模拟 Cube |
| `DeviceMonitor.get_simulated_cube_infos()` | 获取所有模拟 Cube 信息 |
| `DeviceMonitor.get_authenticator_status_description(device_status)` | 解析 Cube 状态位 |
| `DeviceMonitor.get_expiration_status(expired_date_str)` | 判断过期状态（normal/warning/expired） |

#### `src/device_parser.py` — 设备解析器
| 类/方法 | 说明 |
|---|---|
| `DeviceParser.__init__(adb_manager)` | 初始化 await/ready 双队列、分类策略、CubeManager |
| `DeviceParser.start()/stop(join_timeout)` | 启停 worker 线程 + CubeManager |
| `DeviceParser.sync_connected_devices(added_devices, removed_serials)` | 同步设备增删（device_monitor 调用） |
| `DeviceParser.add_device(device)` | 向分类队列添加设备 |
| `DeviceParser.remove_device(serial)` | 从队列移除设备 |
| `DeviceParser.refresh_device(serial)` | 刷新单个设备：ready→await |
| `DeviceParser.reparse_device(serial)` | 激活后重新获取状态（保留 UUID/状态） |
| `DeviceParser.refresh_all_device()` | 刷新全部设备：ready→await |
| `DeviceParser.refresh_all_cube()` | 刷新全部 Cube |
| `DeviceParser.kick_trigger(serial)` | 异步触发 worker 刷新 dirty 设备，先通知 UI 进入刷新态 |
| `DeviceParser._kick(serial)` | 同步执行 refreshDeviceMeta（仅 worker 线程调用） |
| `DeviceParser.get_devices()` | 获取当前显示设备（await+ready，保持顺序） |
| `DeviceParser.get_ready_devices()` | 获取已解析完成设备 |
| `DeviceParser.get_authenticator_serials()` | 获取 Cube serial 列表 |
| `DeviceParser._worker_loop()` | 主循环：分类→kick→await 刷新 |
| `DeviceParser._to_target_device(device)` | DeviceInfo→TargetDeviceAbstract（按 detection_method 分流） |
| `DeviceParser._make_await_device(device)` | 创建刷新中快照（清空 UUID，状态="Checking..."） |
| `DeviceParser._make_unknown_device(device)` | 创建 Unknown 设备 |

#### `src/device_classification_strategy.py` — 设备分类策略
| 类/方法 | 说明 |
|---|---|
| `ClassificationDecision` (dataclass) | 分类决策：ready_device, should_add_cube, should_mark_unknown |
| `DeviceClassificationStrategy.__init__(adb_manager)` | 初始化 |
| `DeviceClassificationStrategy.classify_device(serial, base_device, known_cube, parser_kick)` | 分类设备：ADB→AC8267Device/Cube/Unknown；模拟→SimulatorDevice |
| `DeviceClassificationStrategy.refresh_await_device(serial, current_device)` | 刷新 await 设备（ADB 重新创建，模拟 clone） |

#### `src/target_device.py` — 设备接口与实现
| 类/方法 | 说明 |
|---|---|
| `ITargetDevice` (ABC) | 统一设备接口 |
| `ITargetDevice.CreateSimulation(status, serial_number, uuid, simulate_activate_failure)` | 工厂：创建 SimulatorDevice |
| `ITargetDevice.CreateAdbDevice(serial_number, adb_manager, usb_port)` | 工厂：创建 AC8267Device 或 UnknownAdbDevice |
| `TargetDeviceAbstract` (ABC) | 抽象基类：dirty/lock 状态管理 |
| `TargetDeviceAbstract.markDirty(parser_kick)` | 标记 dirty（lock 状态下延迟） |
| `TargetDeviceAbstract.lock()/unlock(parser_kick)` | 锁定/解锁（unlock 时处理 pending dirty） |
| `TargetDeviceAbstract.isDirty()/isLocked()` | 状态查询 |
| `TargetDeviceAbstract.to_device_info()` | 转换为 DeviceInfo |
| `AC8267Device` (IAdbDevice) | ADB 真实设备 |
| `AC8267Device.refreshDeviceMeta()` | ADB 获取 uuid/status（AuthorizationFailure 跳过） |
| `AC8267Device.getStatusDirect()` | 直接 ADB 获取当前状态 |
| `AC8267Device.activate(signature)` | lock→activate→markDirty→unlock（失败标记 AuthorizationFailure） |
| `UnknownAdbDevice` (IAdbDevice) | 未知 ADB 设备（不可激活） |
| `SimulatorDevice` (TargetDeviceAbstract) | 模拟设备 |
| `SimulatorDevice.activate(signature)` | 模拟激活（支持 simulate_activate_failure） |
| `UnknownDevice` (TargetDeviceAbstract) | 完全未知设备（不可激活） |

#### `src/cube_manager.py` — Cube 快照管理
| 类/方法 | 说明 |
|---|---|
| `CubeManager.__init__(adb_manager, refresh_interval)` | 初始化 Cube 字典、pending/refresh 队列 |
| `CubeManager.start()/stop(join_timeout)` | 启停 worker 线程 |
| `CubeManager.has_cube(serial)` | 判断 serial 是否为已知 Cube |
| `CubeManager.add_cube(serial)` | 添加 Cube 到 pending 队列 |
| `CubeManager.remove_cube(serial)` | 移除 Cube |
| `CubeManager.refresh_cube(serial)` | 刷新单个 Cube |
| `CubeManager.refresh_all_cube()` | 刷新全部 Cube |
| `CubeManager.get_cube_serials()` | 获取所有 Cube serial |
| `CubeManager.get_cubes()` | 获取所有 Cube 快照（deepcopy） |
| `CubeManager._refresh_one(serial)` | 刷新单个 Cube（获取快照→比对变化→通知） |
| `CubeManager._worker_loop()` | 主循环：处理 refresh_queue + 周期刷新 |

#### `src/cube.py` — Cube 抽象与模拟实现
| 类/方法 | 说明 |
|---|---|
| `ICube` (ABC) | Cube 抽象接口：sign_uuid, lock, unlock, activate, config, to_authenticator_info |
| `RealCube(serial, adb_manager)` | 真实 Cube（通过 ADB 通信） |
| `SimulateCube(config)` | 模拟 Cube（P256 签名，本地持久化） |
| `SimulateCube.sign_uuid(uuid_hex)` | P256 ECDSA 签名（counter 递减，持久化） |
| `SimulateCube.create(config)` / `SimulateCube.load(persist_path, private_key_path)` | 创建/加载模拟 Cube |

#### `src/auth_manager.py` — 授权流程编排
| 类/方法 | 说明 |
|---|---|
| `AuthenticationManager.__init__(adb_manager, device_monitor)` | 初始化授权锁、自动授权队列、worker 线程 |
| `AuthenticationManager.is_auto_activation_enabled()` | 查询自动授权开关 |
| `AuthenticationManager.set_auto_activation_enabled(enabled)` | 动态设置自动授权开关 |
| `AuthenticationManager.authenticate_device(device_serial, authenticator_serial, progress_callback)` | 激活单个设备 |
| `AuthenticationManager.authenticate_all_devices(authenticator_serial, progress_callback)` | 批量激活所有未授权设备 |
| `AuthenticationManager._perform_authentication(device_serial, authenticator_serial, progress_callback)` | 核心流程：check state→sign_uuid→log(all/)→double check→activate→log(failure/) |
| `AuthenticationManager._pick_authenticator()` | 选择 time_status=Ready 的 Cube |
| `AuthenticationManager._resolve_cube(serial)` | 解析 Cube（模拟/真实） |
| `AuthenticationManager._resolve_target_device(serial)` | 解析目标设备 |
| `AuthenticationManager.check_device_authentication_status(device_serial, fallback_status)` | 检查设备认证状态 |
| `AuthenticationManager.get_available_authenticators()` | 获取可用 Cube 列表 |
| `AuthenticationManager.get_unauthorized_devices()` | 获取未授权设备列表 |
| `AuthenticationManager.perform_cube_operation(operation, serial, payload)` | 执行 Cube 操作 |
| `AuthenticationManager._on_unauthorized_ready(device)` | 未授权设备入队（自动授权） |
| `AuthenticationManager._activate_worker_loop()` | 自动授权 worker 循环 |
| `AuthenticationManager.is_device_queued_for_auto_activation(serial)` | 查询设备是否在自动授权队列中 |
| `AuthenticationManager.is_device_auto_activation_completed(serial)` | 查询设备自动授权是否完成 |

#### `src/config_manager.py` — 配置管理
| 类/方法 | 说明 |
|---|---|
| `ConfigManager.__init__(config_file)` | 加载 INI 配置文件 |
| `ConfigManager.load_config(config_file)` | 加载配置（不存在则加载默认） |
| `ConfigManager.save_config(config_file)` | 保存配置到文件 |
| `ConfigManager.get/getint/getfloat/getboolean(section, key, fallback)` | 类型化配置读取 |
| `ConfigManager.set(section, key, value)` | 设置配置值 |
| `ConfigManager.get_section(section)` | 获取整个配置节 |
| `ConfigManager.get_status_message(status_code)` | 获取状态码对应消息 |
| `ConfigManager.get_adb_command(command_name, **kwargs)` | 获取 ADB 命令模板并填充参数 |
| `ConfigManager.save_wifi_history/get_wifi_history()` | WiFi 历史记录读写 |

#### `src/log_manager.py` — 日志管理
| 类/方法 | 说明 |
|---|---|
| `LogManager.__init__(config_manager)` | 初始化日志系统（RotatingFileHandler + StreamHandler） |
| `LogManager.setup_logging()` | 配置日志级别、文件、轮转 |
| `LogManager.get_log_content(max_lines)` | 读取日志文件内容 |
| `LogManager.clear_logs()` | 清空日志文件 |
| `LogManager.update_log_level(new_level)` | 动态更新日志级别 |
| `LogManager.update_log_file(new_file)` | 动态更新日志文件路径 |
| `LogManager.log_authorization(success, device_serial, uuid, signature, cube_id, error_reason)` | 记录授权到 detailed_info/all/ |
| `LogManager.log_authorization_failure(device_serial, uuid, signature, cube_id, error_reason, cube_status, cube_expire)` | 记录授权失败到 detailed_info/failure/ |

#### `src/prompt_manager.py` — 国际化文案管理
| 类/方法 | 说明 |
|---|---|
| `PromptManager.__init__(config_path)` | 加载 INI 文案文件 |
| `PromptManager.get(key, default, fallback)` | 获取文案（Section.key 格式） |
| `PromptManager.format(key, default, **kwargs)` | 获取文案并格式化 |

#### `src/main_gui.py` — Tkinter 主窗口
| 类/方法 | 说明 |
|---|---|
| `AuthenticatorToolGUI.__init__()` | 初始化 UI 任务队列、管理器、窗口 |
| `AuthenticatorToolGUI.setup_managers()` | 初始化 ConfigManager→LogManager→ADBManager→DeviceMonitor→AuthenticationManager |
| `AuthenticatorToolGUI.setup_ui()` | 创建菜单栏、主框架、状态栏 |
| `AuthenticatorToolGUI.setup_monitoring()` | 注册回调、启动监控 |
| `AuthenticatorToolGUI._schedule_ui_queue_drain()` | 定时排空 UI 任务队列（16ms 间隔） |
| `AuthenticatorToolGUI._drain_ui_task_queue()` | 从队列取出任务在主线程执行 |
| `AuthenticatorToolGUI.update_device_display(devices)` | 更新设备列表显示（线程安全入队，含状态中文化） |
| `AuthenticatorToolGUI.on_monitor_error(error)` | 处理监控错误（线程安全入队） |
| `AuthenticatorToolGUI.create_menu_bar()` | 创建菜单栏（文件/工具/诊断/帮助/关于） |
| `AuthenticatorToolGUI.apply_configured_theme()` | 从 `[Theme] current` 读取并应用 UI 主题 |
| `AuthenticatorToolGUI.change_theme(theme_name)` | 工具菜单切换主题并保存配置 |
| `AuthenticatorToolGUI._setup_device_tree_tags()` | 配置设备列表颜色标签、字体样式和表头样式（从 [DeviceList] 读取，加载配置后重新应用） |
| `AuthenticatorToolGUI._get_status_tag(status_lower)` | 将设备状态映射为 Treeview tag 名称 |
| `AuthenticatorToolGUI._apply_device_rows(rows)` | 将设备行数据写入 Treeview 并应用颜色标签 |

#### `src/build_options.py` — 构建选项
| 常量 | 说明 |
|---|---|
| `ENABLE_SIMULATED_DEVICE` | 环境变量 CBSS_ENABLE_SIMULATED_DEVICE 控制 |
| `SIMULATED_DEVICE_STATUS_OPTIONS` | 模拟设备状态选项元组 |
| `SIMULATED_AUTHENTICATOR_SERIAL` | 模拟认证器 serial |

### ITargetDevice 核心接口
| 方法 | 说明 |
|---|---|
| `refreshDeviceMeta()` | 获取设备元信息（仅 DeviceParser 调用） |
| `markDirty(kick)` | 标记状态不可信，kick parser 刷新；lock 状态下延迟 |
| `lock()` / `unlock(kick)` | 锁定/解锁；unlock 时检查 pending dirty 并重新标记 |
| `activate(signature)` | lock→activate（失败标记AuthorizationFailure）→markDirty→unlock |
| `isDirty()` / `isLocked()` | 状态查询 |

### 设备状态
- `Authorized` / `Unauthorized` / `Pirated` / `Unknown` / **`AuthorizationFailure`**
- `AuthorizationFailure`：activate 失败后标记，禁止再次激活。UI 显示"未预期失败, 请报告Bug"
- AuthorizationFailure 设备 `refreshDeviceMeta` 跳过 ADB 调用（避免状态被覆盖），仅清除 dirty
- 模拟设备可通过右键"移除模拟设备"重新添加来刷新状态

### 设备状态中文化
- 设备状态显示文本可通过 `config/prompt_chn.ini` 的 `[DeviceStatus]` 节配置：
  - `Authorized = 已授权`
  - `Unauthorized = 未授权`
  - `AuthorizationFailure = 授权失败`
  - `Pirated = 异常设备`
  - `Unknown = 未知`
  - `Checking = 检测中...`
- 状态翻译在 `update_device_display()` 中通过 `PromptManager.get()` 获取
- 内部逻辑判断仍使用英文原始状态值（通过隐藏列 `status_lower` 传递）

### 设备列表显示配置
- 通过 `config/default_config.ini` 的 `[DeviceList]` 节配置设备列表显示样式：
  - `font_size`：字体大小（默认 12）
  - `font_bold`：是否加粗（默认 false）
  - `color_authorized`：已授权设备字体颜色（默认 #008000 绿色）
  - `color_unauthorized`：未授权设备字体颜色（默认 #000000 黑色）
  - `color_authorization_failure`：授权失败设备字体颜色（默认 #FF0000 红色）
  - `color_pirated`：异常设备字体颜色（默认 #8B4513 褐色）
- 设备列表占位文本（如 UUID 不可用/获取中）通过 `config/prompt_chn.ini` 的 `[DeviceTable]` 节配置
- 颜色通过 `ttk.Treeview` 的 `tag_configure` 实现，在 `_setup_device_tree_tags()` 中初始化；同时清理 `DeviceList.Treeview` 未选中行的 foreground/background map，避免 Windows ttk 主题覆盖 tag 颜色；加载新配置后会重新应用
- 字体大小和加粗通过 `ttk.Style` 的 `configure` 设置到列表和表头，行高自动适配字体大小
- `ConfigManager._migrate_config_defaults()` 会将历史默认盗版颜色 `#FFD700` 迁移为 `#8B4513`，其它自定义颜色保持不变

### Cube 状态信息栏显示配置
- 通过 `config/default_config.ini` 的 `[CubeStatusInfo]` 节配置 Cube 信息区域的显示样式：
  - `font_size`：状态信息值字体大小（默认 10）
  - `authorized_count_color`：已授权数字体颜色（默认 #0000FF 蓝色）
  - `remaining_low_color`：剩余可授权数 low 状态颜色，剩余 < 50（默认 #FF0000 红色）
  - `remaining_medium_color`：剩余可授权数 medium 状态颜色，50 <= 剩余 < 100（默认 #FFD700 黄色）
  - `remaining_high_color`：剩余可授权数 high 状态颜色，剩余 >= 100（默认 #008000 绿色）
- `AuthenticatorToolGUI._setup_cube_status_info_style()` 在创建 UI 和加载配置后应用字体与固定颜色
- `AuthenticatorToolGUI._update_cube_count_colors()` 在 Cube 信息刷新时按剩余可授权数更新颜色

### UI 主题配置
- 通过 `config/default_config.ini` 的 `[Theme] current` 配置启动主题，默认 `modern`
- 工具菜单 `主题选择` 可切换主题并立即保存配置
- 自定义主题：`modern` / `aero` / `light` / `dark`
- 原生主题：运行时通过 `ttk.Style().theme_names()` 动态读取并加入菜单（如 `clam` / `vista` / `alt` / `classic` / `xpnative` 等，取决于当前 Tk 环境）
- 兼容历史/误拼写 `moderm`，内部会归一为 `modern`
- `modern` / `aero` / `light` / `dark` 使用独立 `cbss-*` ttk 主题，避免污染 `clam` / `vista` 等原生主题
- `aero` 为浅蓝灰 Windows 风格主题，匹配浅蓝灰背景、白色输入区域和蓝色强调色

### DeviceParser kick 操作
- `kick()` 遍历 ready/await 队列中所有 dirty 设备，调用 `refreshDeviceMeta`
- `markDirty` 通过 `parser_kick` 回调触发

### 日志增强
- `logs/detailed_info/all/authorization_xxxxxx.json` — 所有授权记录
  - 字段：success, timestamp, serial_id, uuid, signature, cube_id, error_reason
- `logs/detailed_info/failure/authorization_xxxxxx.json` — 失败记录
  - 额外字段：cube_status, cube_expire
- 目录路径可通过 `[Logging] auth_log_all_dir` / `auth_log_failure_dir` 配置
- 每文件 200 条，自动轮转

---

## cbss_tools 相关改动的标准落点
凡是新增/修改设备能力，按以下顺序改：
1. 在 `config/default_config.ini` 的 `[ADB_Commands]` 新增命令模板。
2. 在 `src/adb_manager.py` 增加同名封装方法（只走 `execute_adb_command()`）。
3. 在 `src/main_gui.py` 或 `src/diaglog/` 接入 UI 入口（菜单/对话框/进度反馈）。
4. 如涉及文案，更新 `config/prompt_chn.ini`，通过 `PromptManager.get()` 取文案。

禁止：在 UI 层直接写 `subprocess` 或硬编码 ADB 命令。

## 输出解析规则（易踩坑）
- 命令成功判定依赖工具输出中的：
  - `[status] <code>[, message]`
  - `[result] <payload>`
- 解析逻辑在 `ADBManager._parse_command_output()`。
- 若 `status_code != 0`，错误文案优先来自 `[status]`，其次回落到 `Status_Messages` 配置。

## 并发与 UI 更新规则
- 长耗时操作必须放在线程中执行。
- 线程内更新 UI 必须使用 `root.after(...)` 或 `dialog.after(...)` 回主线程。
- 设备分类误判修复依赖 `DeviceParser.sync_connected_devices()` 与 `_worker_loop()` 的重分类逻辑，不要轻易删除重试队列。

## 联调与回归清单
- 本地运行：`python main.py`
- 打包：`python package_all.py --type release`
- 清理：`python package_all.py --clean`
- 压测/签名验证：`python stress_test/quick_stress_test.py`

回归重点：
1. 认证器不会出现在 target 列表中（尤其 snapshot 瞬时失败时）。
2. 单设备授权与批量授权流程均可闭环。
3. Wi-Fi 连接后 `time_status` / 网络连通性状态更新正常。
4. 日志写入 `logs/cbss_tool.log`，异常可定位。

## 平台与依赖边界
- Windows 优先，ADB 默认路径：`adb/adb.exe`。
- 设备侧依赖：`cbss_tools`、`cbss_host_tool`。
- 诊断与网络相关能力依赖 `default_config.ini` 中的命令模板与 `Network` 配置。

## 维护方法

### 维护建议
- 做新功能先扩展配置，再扩展 `ADBManager`，最后接 UI。
- 保持 `DeviceMonitor -> DeviceParser -> CubeManager` 边界清晰，避免把分类与快照逻辑挪回 UI。
- 对外行为变化（菜单、提示、错误）一律走 `prompt_chn.ini`，避免硬编码中文。
- 完成新功能开发后agent需要更新agent_guide.md中的架构设计
- 提示词出现强制要求后，更新相关维护建议到强制要求中

### 强制要求
- UI代码与逻辑代码分离维护
- 改动前需要根据架构设计，确认功能不会导致功能失效
- 任何ITargetDevice的子类(包括SimulatorDevice, AdbDevice等)需要统一管理，除Classification以及UI外，不应该在任何非子类代码中体现中差异。
- 完成新功能开发后，在tests/下增加该功能测试case, 并需要确保tests/下全部case通过
- 完成Bug修复后，需要确保tests/下全部case通过

### 单元测试

#### 测试框架
- 基于 Python 标准库 `unittest`
- 测试文件位于 `tests/` 目录，命名规范 `test_<模块名>.py`
- 使用 Mock/Fake 对象替代真实 ADB/设备依赖，确保测试可离线运行

#### 运行方式

**一键运行全部测试：**
```bash
python run_unittest.py
```

**按模块过滤运行：**
```bash
python run_unittest.py test_auth_manager          # 运行指定模块全部测试
python run_unittest.py test_concurrent            # 运行并发测试模块
```

**按测试类过滤运行：**
```bash
python run_unittest.py test_concurrent.TestConcurrentDeviceAddRemove
```

**按单个测试方法过滤运行：**
```bash
python run_unittest.py test_concurrent.TestConcurrentDeviceAddRemove.test_concurrent_add_multiple_devices
```

**使用标准 unittest 运行：**
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

#### 测试模块清单

| 测试文件 | 覆盖模块 | 测试数 | 说明 |
|---|---|---|---|
| `test_adb_manager.py` | `src/adb_manager.py` | 7 | ADB 命令执行、输出解析、DeviceInfo/AuthenticatorInfo 数据结构 |
| `test_device_source.py` | `src/device_source.py` | 8 | AdbDeviceDetector 增删检测、SimulatorDeviceDetector 增删管理 |
| `test_device_monitor.py` | `src/device_monitor.py` | 6 | 设备监控启停、回调注册、设备增删同步 |
| `test_device_parser.py` | `src/device_parser.py` | 12 | 设备分类、await/ready 队列、kick 刷新、增删同步 |
| `test_device_classification.py` | `src/device_classification_strategy.py` | 8 | 设备分类策略、ADB/模拟设备分流、状态刷新 |
| `test_target_device.py` | `src/target_device.py` | 10 | ITargetDevice 接口、dirty/lock 状态机、activate 流程、SimulatorDevice |
| `test_cube_manager.py` | `src/cube_manager.py` | 8 | Cube 快照管理、增删刷新、周期轮询 |
| `test_cube.py` | `src/cube.py` | 2 | SimulateCube 签名验证、持久化、认证流程集成 |
| `test_auth_manager.py` | `src/auth_manager.py` | 5 | 授权流程、自动授权队列、Cube 选择、状态检查 |
| `test_config_manager.py` | `src/config_manager.py` | 12 | 配置读写、默认值、WiFi 历史、ADB 命令模板 |
| `test_log_manager.py` | `src/log_manager.py` | 8 | 日志初始化、授权记录、日志读取 |
| `test_prompt_manager.py` | `src/prompt_manager.py` | 5 | 国际化文案读取、格式化 |
| `test_build_options.py` | `src/build_options.py` | 4 | 构建选项、模拟设备状态常量 |
| `test_concurrent.py` | 并发场景 | 12 | 并发增删设备、并发 markDirty/lock、CubeManager 并发、授权锁线程安全、自动授权队列线程安全、DeviceParser kick 并发、Detector 轮询并发、deepcopy 线程安全 |
| `test_stress_auto_auth.py` | 压力测试 | 16 | 自动授权高并发入队、队列一致性、设备移除并发安全、无认证盒子重试、竞态条件、真实激活流程并发、快速开关切换、部分失败场景、Worker 重启 |
| `test_main_gui.py` | `src/main_gui.py` | 30 | UI 任务队列、线程安全入队、设备显示更新 |

#### 添加新测试
1. 在 `tests/` 下创建 `test_<模块名>.py`
2. 继承 `unittest.TestCase`，方法名以 `test_` 开头
3. 使用 Fake 对象模拟外部依赖（ADB、文件系统、网络等）
4. 运行 `python run_unittest.py` 确保全部通过

#### 并发测试注意事项
- 并发测试使用 `threading.Thread` 模拟多线程场景
- 使用 `time.sleep` + 轮询等待异步操作完成
- 验证线程安全：锁机制、队列操作、共享状态一致性
- 并发 deepcopy 测试验证数据隔离性

#### 压力测试（test_stress_auto_auth.py）
压力测试专注于自动授权场景下的并发安全性验证，基于 `src/` 下现有组件实现：

- **SimulatorCube** 作为认证盒子（Cube），提供模拟的签名验证和激活能力
- **SimulatorDevice** 作为待激活设备，支持模拟激活成功/失败
- **SimulatorDeviceDetector** 管理模拟设备的增删
- **DeviceMonitor** 提供设备监控和回调机制
- **AuthenticationManager** 的自动授权队列和工作线程

**测试分类：**

| 测试类 | 测试数 | 说明 |
|---|---|---|
| `TestStressAutoAuthHighVolume` | 3 | 高并发入队（50设备）、重复序列号防护、队列一致性 |
| `TestStressAutoAuthDeviceRemoval` | 2 | 设备移除并发安全、队列中设备被移除 |
| `TestStressAutoAuthNoAuthenticator` | 2 | 无认证盒子时重试不崩溃、中途出现认证盒子 |
| `TestStressAutoAuthRaceConditions` | 3 | 多线程回调竞态、队列锁竞争、`is_device_queued` 线程安全 |
| `TestStressAutoAuthRealActivation` | 3 | 真实激活流程并发（20设备）、快速开关切换、部分激活失败 |
| `TestStressAutoAuthToggle` | 3 | 开关切换期间入队、快速启停、Worker 重启恢复 |

**运行方式：**
```bash
python run_unittest.py test_stress_auto_auth
```

### 版本管理
- 完成新功能开发后，更新次设备号
- 完成bug修复后，更新修订号
- 修改版本后，将更新内容更新到Changelog.md
