# cbss_tools 维护 Skill

## 目标
用于指导维护 `cbss_tools` / `cbss_host_tool` 相关 PC 端代码（The Cube）时的分析与改动路径，确保新增能力可落在现有架构中。本文档同时是全量功能清单，便于快速定位。

---

## 一、全量架构（v3.2.2）

### 数据流
1. **设备探测**：`DeviceMonitor` 通过 `IDeviceDetector` 列表轮询：
   - `AdbDeviceDetector` — ADB 设备（对比上次 serial 列表，上报增删）
   - `SimulatorDeviceDetector` — 模拟设备（用户操作触发 pending 增删事件）
   - Detector 通过 `poll_changes()` 返回 `DeviceChange(added, removed)`，仅上报变化
2. **设备管理**：`DeviceMonitor` 维护 `_connected_index` 统一记录所有探测器上报的设备
   - 仅 `_monitor_loop` 调用 `_update_device_info` 轮询各 Detector 的 `poll_changes()`
   - 仅将增删变化（`added`/`removed`）传递给 `sync_connected_devices`，不刷新全部设备
3. **设备分类**：`DeviceParser` 将序列号分流为 authenticator / target，维护 `await/ready` 队列。
   - `_to_target_device` 不区分 sim/adb 类型，统一创建 `UnknownDevice`/`UnknownAdbDevice`
   - `DeviceClassificationStrategy.classify_device` 负责创建 `SimulatorDevice`（含 `simulate_activate_failure`）
   - 分类完成后在 worker loop 中 `markDirty(kick)`，触发 `refreshDeviceMeta` 获取元信息
   - `refreshDeviceMeta` 前后记录 INFO 日志
4. **认证器快照**：`CubeManager` 周期刷新 `snapshot`（仅 Cube，不刷新 target 设备）。
5. **授权流程**：`AuthenticationManager._perform_authentication()` 执行：
   `check state → sign_uuid → log(all/) → double check → activate → log(failure/)`
   - sign_uuid 前必须先确认 device 状态为 Unauthorized，避免消耗 Cube 授权数
   - activate 失败标记 `AuthorizationFailure` 状态，禁止再次授权
   - 失败记录写入 `detailed_info/failure/`，含 Cube status/expire
6. **刷新机制**（仅通过 `markDirty` 触发）：
   - 新增设备 → `markDirty`（worker loop 中）
   - 用户按钮刷新 → 全部设备 `markDirty` + `kick`
   - 授权完成/失败 → `mark_device_dirty(serial)`
   - `_submitted` 标记防止重复加入自动授权队列

### 关键文件
- `src/device_source.py` — `IDeviceDetector` 抽象 + `AdbDeviceDetector` + `SimulatorDeviceDetector`
- `src/device_monitor.py` — 设备监控，统一管理所有探测器
- `src/device_parser.py` — 设备分类 + dirty 设备 kick 刷新
- `src/device_classification_strategy.py` — 分类策略，分类后 markDirty
- `src/target_device.py` — `ITargetDevice` 接口 + dirty/lock 状态管理
- `src/cube_manager.py` — Cube 快照管理
- `src/auth_manager.py` — 授权流程编排
- `src/main_gui.py` — Tkinter 主窗口

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

## 二、cbss_tools 相关改动的标准落点
凡是新增/修改设备能力，按以下顺序改：
1. 在 `config/default_config.ini` 的 `[ADB_Commands]` 新增命令模板。
2. 在 `src/adb_manager.py` 增加同名封装方法（只走 `execute_adb_command()`）。
3. 在 `src/main_gui.py` 或 `src/diaglog/` 接入 UI 入口（菜单/对话框/进度反馈）。
4. 如涉及文案，更新 `config/prompt_chn.ini`，通过 `PromptManager.get()` 取文案。

禁止：在 UI 层直接写 `subprocess` 或硬编码 ADB 命令。

## 三、输出解析规则（易踩坑）
- 命令成功判定依赖工具输出中的：
  - `[status] <code>[, message]`
  - `[result] <payload>`
- 解析逻辑在 `ADBManager._parse_command_output()`。
- 若 `status_code != 0`，错误文案优先来自 `[status]`，其次回落到 `Status_Messages` 配置。

## 四、并发与 UI 更新规则
- 长耗时操作必须放在线程中执行。
- 线程内更新 UI 必须使用 `root.after(...)` 或 `dialog.after(...)` 回主线程。
- 设备分类误判修复依赖 `DeviceParser.sync_connected_devices()` 与 `_worker_loop()` 的重分类逻辑，不要轻易删除重试队列。

## 五、联调与回归清单
- 本地运行：`python main.py`
- 打包：`python package_all.py --type release`
- 清理：`python package_all.py --clean`
- 压测/签名验证：`python stress_test/quick_stress_test.py`

回归重点：
1. 认证器不会出现在 target 列表中（尤其 snapshot 瞬时失败时）。
2. 单设备授权与批量授权流程均可闭环。
3. Wi-Fi 连接后 `time_status` / 网络连通性状态更新正常。
4. 日志写入 `logs/cbss_tool.log`，异常可定位。

## 六、平台与依赖边界
- Windows 优先，ADB 默认路径：`adb/adb.exe`。
- 设备侧依赖：`cbss_tools`、`cbss_host_tool`。
- 诊断与网络相关能力依赖 `default_config.ini` 中的命令模板与 `Network` 配置。

## 七、维护建议（针对本项目）
- 做新功能先扩展配置，再扩展 `ADBManager`，最后接 UI。
- 保持 `DeviceMonitor -> DeviceParser -> CubeManager` 边界清晰，避免把分类与快照逻辑挪回 UI。
- 对外行为变化（菜单、提示、错误）一律走 `prompt_chn.ini`，避免硬编码中文。