# Agent Requirements (Updated 2026-05-11)

## 当前问题要求
- 修复“无法自动授权”问题，确保 `SimulatorDevice` 自动授权按预期成功/失败。
- `SimulatorTargetDevice` 与 `SimulatorCube` 仅用于调试；除 UI 与 Simulator 相关类外，不在核心逻辑中做区分分支。
- 继续推进 UI 代码与核心逻辑抽离。
- 在 `SimulatorTargetDevice` 内部保持状态，设备解析流程不得重置该状态。
- 排查并移除核心逻辑中不必要的 Simulator 区分代码，迁移到 Simulator 相关类或 UI 层。
- 修复并通过相关单元测试。

## 版本与交付要求
- 版本格式：`major.minor.bug_fix`。
- 本次为 Bug Fix，`bug_fix` 版本号递增。
- 变更后更新 `changelog/CHANGELOG.md`。
