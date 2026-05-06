# cbss_tools 维护 Skill

## 目标
用于指导维护 `cbss_tools/cbss_host_tool` 相关 PC 端代码（The Cube）时的分析与改动路径，确保新增能力可落在现有架构中。

## 一、先理解的数据流（必须）
1. 设备发现：`DeviceMonitor` 轮询 `adb devices -l`。
2. 设备分类：`DeviceParser` 将序列号分流为 authenticator / target，维护 `await/ready` 队列。
3. 认证器快照：`CubeManager` 周期刷新 `snapshot`，并通过回调更新 UI。
4. 授权流程：`AuthenticationManager._perform_authentication()` 执行
   `acquire_secure_uuid -> sign -> activate_device2 -> state校验`。

关键文件：
- `src/device_monitor.py`
- `src/device_parser.py`
- `src/cube_manager.py`
- `src/auth_manager.py`
- `src/main_gui.py`

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