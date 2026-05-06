# Copilot instructions for cbss_tool_latest

## Project snapshot
- This is a Windows-first Tkinter desktop app for AC8267 authorization workflows over ADB (`main.py`, `src/main_gui.py`).
- Runtime behavior is config-driven from `config/default_config.ini` (ADB command templates, refresh rates, status code messages, network checks).
- UI text is i18n-style and mostly sourced from `config/prompt_chn.ini` via `PromptManager` (`Section.key` lookups).

## Core architecture (read before editing)
- `AuthenticatorToolGUI` orchestrates everything: manager wiring, Tk widgets, menu actions, monitor callbacks, and operation locking (`src/main_gui.py`).
- Device discovery is split into stages:
  1) `DeviceMonitor` polls `adb devices -l` and syncs connected serials.
  2) `DeviceParser` classifies each serial as authenticator vs target and maintains await/ready queues.
  3) `CubeManager` owns periodic authenticator snapshot refreshes.
- Authorization flow is centralized in `AuthenticationManager._perform_authentication()`:
  `device_uuid -> authenticator_sign -> device_activate -> state verification` (`src/auth_manager.py`).
- All ADB calls should go through `ADBManager` (do not scatter raw subprocess calls in UI code).

## Codebase-specific conventions
- Keep long-running work off the Tk main thread; worker threads must marshal UI updates with `root.after(...)`.
- `src/diaglog/` is the active dialog package (note the spelling); `src/dialog/` is empty/unused.
- Status parsing relies on device tool output markers (`[status]`, `[result]`) in `ADBManager._parse_command_output()`.
- Use config templates for device commands (`ConfigManager.get_adb_command()`), not hardcoded shell strings.
- Authenticator misclassification is intentionally mitigated by reclassification/retry logic in `DeviceParser.sync_connected_devices()` and `_worker_loop()`.

## Developer workflows
- Run app locally: `python main.py`
- Build packages/exe: `python package_all.py --type all|dev|lite|portable|installer|release`
- Clean build artifacts: `python package_all.py --clean`
- PyInstaller baseline is `cbss_simple.spec`; packaging script can regenerate spec dynamically (`package_all.py`).
- Stress/crypto validation script exists at `stress_test/quick_stress_test.py` (requires connected devices and `stress_test/pubkey/pub.pem`).

## Integration points and external dependencies
- External tooling: bundled ADB binaries under `adb/` (default path `adb/adb.exe`).
- Device-side commands expect `cbss_tools` and `cbss_host_tool` availability (see `[ADB_Commands]` in `config/default_config.ini`).
- Network readiness checks use ping hosts from config (`[Network]`), with a critical host gate (`ntp.ntsc.ac.cn` by default).
- Logging is centralized via `LogManager` with rotating file output (`logs/cbss_tool.log`).

## Editing guidance for agents
- If adding a new device operation, add command template in `config/default_config.ini` + wrapper method in `ADBManager` + UI action/dialog hook.
- If adding/changing user-facing text, update `config/prompt_chn.ini` and fetch it through `PromptManager` (avoid hardcoded Chinese strings).
- Preserve queue/callback boundaries (`DeviceMonitor` ↔ `DeviceParser` ↔ `CubeManager`) to avoid regressions in device list flicker or misclassification.
