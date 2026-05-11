"""
激活管理器
负责处理设备激活流程
"""
import logging
import queue
import threading
import time
import os
import json
from datetime import datetime
from typing import List, Optional, Callable, Dict
from .adb_manager import ADBManager, DeviceInfo, AuthenticatorInfo
from .device_monitor import DeviceMonitor
from .build_options import ENABLE_SIMULATED_DEVICE
from .target_device import AC8267Device, ITargetDevice
from .cube import ICube, RealCube


class AuthenticationManager:
    _READY_TIME_STATUS = "ready"
    _CRITICAL_BUG_LOG_PATH = os.path.join("logs", "critical_bug.log")

    def __init__(self, adb_manager: ADBManager, device_monitor: DeviceMonitor):
        self.adb_manager = adb_manager
        self.device_monitor = device_monitor

        self._authentication_lock = threading.Lock()
        self._is_authenticating = False

        # 自动授权功能
        self._auto_activation_enabled = self.device_monitor.config.getboolean('General', 'auto_activation_enabled', False)
        self._activate_queue: queue.Queue[Optional[str]] = queue.Queue()
        self._queued_serials = set()
        self._in_progress_serials = set()
        self._auto_activation_completed_serials = set()
        self._queue_lock = threading.Lock()
        self._blocked_lock = threading.Lock()
        self._worker_running = False
        self._worker_thread = None
        self._stop_event = threading.Event()
        self._blocked_activation_devices: Dict[str, Dict[str, str]] = {}
        self._simulated_lock = threading.Lock()
        self._simulated_cubes: Dict[str, ICube] = {}
        self._simulated_cube_counter = 0

        # 始终注册回调，是否入队由开关控制
        self.device_monitor.device_parser.add_callback('unauthorized_ready', self._on_unauthorized_ready)
        add_callback = getattr(self.device_monitor, "add_callback", None)
        if callable(add_callback):
            self.device_monitor.add_callback('device_update', self._on_device_update)

        if self._auto_activation_enabled:
            self._start_activate_worker()

    def is_auto_activation_enabled(self) -> bool:
        """是否启用自动授权"""
        return self._auto_activation_enabled

    def set_auto_activation_enabled(self, enabled: bool):
        """动态设置自动授权开关"""
        enabled = bool(enabled)
        if self._auto_activation_enabled == enabled:
            return

        self._auto_activation_enabled = enabled
        if enabled:
            self._start_activate_worker()
            self._enqueue_existing_unauthorized_devices()
            logging.info("自动授权功能已启用")
        else:
            self._clear_activate_queue()
            self.stop()
            logging.info("自动授权功能已禁用")

    def _clear_activate_queue(self):
        """清空自动授权队列与状态"""
        with self._queue_lock:
            self._queued_serials.clear()
            self._in_progress_serials.clear()
            self._auto_activation_completed_serials.clear()

        while True:
            try:
                self._activate_queue.get_nowait()
            except queue.Empty:
                break

    def _enqueue_existing_unauthorized_devices(self):
        """开关开启时补齐当前未授权设备到队列"""
        try:
            for device in self.get_unauthorized_devices():
                self._on_unauthorized_ready(device)
        except Exception as e:
            logging.error(f"补齐自动授权队列失败: {e}")

    def stop(self, join_timeout: float = 30.0):
        """停止后台线程，确保 worker 完全退出后才返回"""
        if not self._worker_running:
            return
        self._worker_running = False
        self._stop_event.set()
        # 发送哨兵值，快速唤醒队列阻塞
        self._activate_queue.put(None)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=max(float(join_timeout or 0), 0.0))
            if self._worker_thread.is_alive():
                logging.warning("worker 线程在超时内未能完全退出")

    def _start_activate_worker(self):
        # 若旧线程仍存活（stop() 尚未完全返回或超时），拒绝启动第二个 worker
        if self._worker_thread and self._worker_thread.is_alive():
            logging.warning("上一个 worker 线程仍在运行，拒绝启动新线程")
            return
        if self._worker_running:
            return
        self._stop_event.clear()
        self._worker_running = True
        self._worker_thread = threading.Thread(target=self._activate_worker_loop, daemon=True)
        self._worker_thread.start()
        logging.info("自动授权 activate_worker 已启动")

    def _on_unauthorized_ready(self, device: DeviceInfo):
        """DeviceParser解析完成后，将未授权设备加入自动授权队列"""
        try:
            if not self._auto_activation_enabled or not device:
                return
            serial = str(device.serial or "").strip()
            if not serial:
                return
            if self.is_device_activation_blocked(serial):
                return
            if not (device.status and device.status.strip().lower() == "unauthorized"):
                return
            if not device.uuid:
                return

            with self._queue_lock:
                if serial in self._queued_serials or serial in self._in_progress_serials:
                    return
                self._auto_activation_completed_serials.discard(serial)
                self._queued_serials.add(serial)

            self._activate_queue.put(serial)
            logging.info(f"未授权设备已加入自动授权队列: {serial}")
        except Exception as e:
            logging.error(f"提交自动授权队列失败: {e}")

    def _on_device_update(self, devices: List[DeviceInfo]):
        current_serials = {str((d.serial if d else "") or "").strip() for d in (devices or [])}
        with self._blocked_lock:
            stale = [serial for serial in self._blocked_activation_devices.keys() if serial not in current_serials]
            for serial in stale:
                self._blocked_activation_devices.pop(serial, None)
                logging.info("检测到设备插拔，已解除激活失败锁定: %s", serial)

    def is_device_activation_blocked(self, serial: str) -> bool:
        key = str(serial or "").strip()
        if not key:
            return False
        with self._blocked_lock:
            return key in self._blocked_activation_devices

    def _record_critical_activation_bug(self, serial: str, uuid: str, signature: str, message: str, details: str = ""):
        payload = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "serial": str(serial or ""),
            "uuid": str(uuid or ""),
            "signature": str(signature or ""),
            "message": str(message or ""),
            "details": str(details or ""),
        }
        log_path = self._CRITICAL_BUG_LOG_PATH
        parent = os.path.dirname(log_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        logging.critical(
            "CRITICAL BUG: 激活失败设备已锁定，需插拔后重试 serial=%s uuid=%s signature=%s message=%s",
            payload["serial"],
            payload["uuid"],
            payload["signature"],
            payload["message"],
        )

    def _mark_activation_failed_and_block(self, serial: str, uuid: str, signature: str, message: str, details: str = ""):
        with self._blocked_lock:
            self._blocked_activation_devices[str(serial or "").strip()] = {
                "uuid": str(uuid or ""),
                "signature": str(signature or ""),
                "message": str(message or ""),
            }
        try:
            self._record_critical_activation_bug(serial=serial, uuid=uuid, signature=signature, message=message, details=details)
        except Exception as e:
            logging.error("记录CRITICAL BUG日志失败: %s", e)

    def _pick_authenticator(self) -> Optional[str]:
        ready_authenticators = []
        for serial in self.get_available_authenticators():
            if self.is_simulated_cube(serial):
                ready_authenticators.append(serial)
                continue
            auth_info = self.device_monitor.get_authenticator_by_serial(serial)
            time_status = self._normalize_status(getattr(auth_info, 'time_status', ''))
            if time_status == self._READY_TIME_STATUS:
                ready_authenticators.append(serial)

        if not ready_authenticators:
            return None
        # 固定顺序选择，避免来回切换
        return sorted(ready_authenticators)[0]

    def _is_device_still_unauthorized(self, serial: str) -> bool:
        try:
            device = self.device_monitor.get_device_by_serial(serial)
            if not device:
                return False
            status = (device.status or "").strip().lower()
            return status == "unauthorized" and bool(device.uuid)
        except Exception:
            return False

    def _activate_worker_loop(self):
        while self._worker_running and not self._stop_event.is_set():
            serial = None
            try:
                # 0.2s timeout keeps the stop-event check responsive without significant CPU overhead
                serial = self._activate_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # 停止哨兵 — break 退出循环
            if serial is None:
                break

            serial = str(serial or "").strip()
            if not serial:
                continue

            # 设备状态变化后无需处理
            if not self._is_device_still_unauthorized(serial):
                with self._queue_lock:
                    self._queued_serials.discard(serial)
                continue

            authenticator_serial = self._pick_authenticator()
            if not authenticator_serial:
                # Cube不可用，稍后重试
                time.sleep(1.0)
                if self._is_device_still_unauthorized(serial):
                    with self._queue_lock:
                        if serial not in self._queued_serials and serial not in self._in_progress_serials:
                            self._queued_serials.add(serial)
                            self._activate_queue.put(serial)
                continue

            with self._queue_lock:
                if serial in self._in_progress_serials:
                    continue
                self._queued_serials.discard(serial)
                self._in_progress_serials.add(serial)

            try:
                result = self._run_authentication(serial, authenticator_serial)
                if result.get('success'):
                    logging.info(f"自动授权成功: {serial}")
                    with self._queue_lock:
                        self._auto_activation_completed_serials.add(serial)
                else:
                    logging.warning(f"自动授权失败: {serial}, {result.get('message', '')}")

                # 自动授权后刷新 Cube 和当前 Target Device（仅在未停止时执行）
                if self._worker_running and not self._stop_event.is_set():
                    self.device_monitor.refresh_all_cube()
                    self.device_monitor.refresh_device(serial)
            except Exception as e:
                logging.error(f"自动授权执行异常: {serial}, {e}")
            finally:
                with self._queue_lock:
                    self._in_progress_serials.discard(serial)

    def is_authenticating(self) -> bool:
        """检查是否正在执行激活"""
        return self._is_authenticating

    def is_simulation_enabled(self) -> bool:
        """是否启用模拟功能（编译/打包选项）"""
        return ENABLE_SIMULATED_DEVICE

    def _resolve_target_device(self, device_serial: str) -> ITargetDevice:
        """Resolve target device instance by serial for unified authentication flow."""
        serial = str(device_serial or "").strip()
        target_getter = getattr(self.device_monitor, "get_target_device", None)
        if callable(target_getter):
            existing_target = target_getter(serial)
            if existing_target is not None:
                return existing_target

        device_info = None
        getter = getattr(self.device_monitor, "get_device_by_serial", None)
        if callable(getter):
            device_info = getter(serial)

        target_device = ITargetDevice.CreateAdbDevice(serial, self.adb_manager)
        if not isinstance(target_device, AC8267Device):
            target_device = AC8267Device(
                serial_number=serial,
                adb_manager=self.adb_manager,
                uuid=(device_info.uuid if device_info else ""),
                status=(device_info.status if device_info else "Unknown")
            )
        if not target_device.getUuid() and device_info and device_info.uuid:
            target_device.setUuid(device_info.uuid)
        return target_device

    def authenticate_device(self, device_serial: str, authenticator_serial: str,
                          progress_callback: Optional[Callable] = None) -> dict:
        """
        激活单个设备

        Args:
            device_serial: 待激活设备序列号
            authenticator_serial: 激活盒子序列号
            progress_callback: 进度回调函数

        Returns:
            dict: 激活结果 {'success': bool, 'message': str, 'details': str}
        """
        return self._run_authentication(device_serial, authenticator_serial, progress_callback)

    def _run_authentication(self, device_serial: str, authenticator_serial: str,
                            progress_callback: Optional[Callable] = None) -> dict:
        """串行执行激活流程，避免并发冲突"""
        with self._authentication_lock:
            if self._is_authenticating:
                return {
                    'success': False,
                    'message': '正在执行其他激活操作，请稍后重试',
                    'details': ''
                }

            self._is_authenticating = True

        try:
            return self._perform_authentication(device_serial, authenticator_serial, progress_callback)
        finally:
            self._is_authenticating = False

    def authenticate_all_devices(self, authenticator_serial: str,
                               progress_callback: Optional[Callable] = None) -> dict:
        """
        激活所有未激活设备

        Args:
            authenticator_serial: 激活盒子序列号
            progress_callback: 进度回调函数

        Returns:
            dict: 激活结果统计
        """
        with self._authentication_lock:
            if self._is_authenticating:
                return {
                    'success': False,
                    'message': '正在执行其他激活操作，请稍后重试',
                    'total': 0,
                    'success_count': 0,
                    'failed_count': 0,
                    'results': []
                }

            self._is_authenticating = True

        try:
            # 获取所有未激活设备（仅已完成解析的ready设备）
            unauthorized_devices = self.get_unauthorized_devices()

            if not unauthorized_devices:
                return {
                    'success': True,
                    'message': '没有需要激活的设备',
                    'total': 0,
                    'success_count': 0,
                    'failed_count': 0,
                    'results': []
                }

            results = []
            success_count = 0
            failed_count = 0

            for i, device in enumerate(unauthorized_devices):
                if progress_callback:
                    progress_callback(f"正在激活设备 {device.serial} ({i+1}/{len(unauthorized_devices)})")

                result = self._perform_authentication(device.serial, authenticator_serial)
                results.append({
                    'device_serial': device.serial,
                    'success': result['success'],
                    'message': result['message']
                })

                if result['success']:
                    success_count += 1
                else:
                    failed_count += 1

            return {
                'success': success_count > 0,
                'message': f'批量激活完成: 成功 {success_count}，失败 {failed_count}',
                'total': len(unauthorized_devices),
                'success_count': success_count,
                'failed_count': failed_count,
                'results': results
            }

        finally:
            self._is_authenticating = False

    def _perform_authentication(self, device_serial: str, authenticator_serial: str,
                              progress_callback: Optional[Callable] = None) -> dict:
        """执行单个设备的激活流程"""
        try:
            logging.info(f"开始激活设备: {device_serial}")
            blocked_msg = "设备上次激活失败，已锁定；请先插拔设备后再尝试激活"
            if self.is_device_activation_blocked(device_serial):
                logging.warning("拒绝激活已锁定设备: %s", device_serial)
                return {
                    'success': False,
                    'message': blocked_msg,
                    'details': ''
                }

            # 步骤1: 获取设备UUID
            cube = self._resolve_cube(authenticator_serial)
            target_device = self._resolve_target_device(device_serial)
            if progress_callback:
                progress_callback("正在获取设备UUID...")

            device_uuid = target_device.getUuid()
            if not device_uuid:
                if target_device.getDetectionMethod().strip().lower() != "adb":
                    error_msg = "设备UUID为空"
                    logging.error(error_msg)
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': ''
                    }
                uuid_result = self.adb_manager.get_device_uuid(device_serial)
                if not uuid_result.success:
                    error_msg = f"获取设备UUID失败: {uuid_result.error_message}"
                    logging.error(error_msg)
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': uuid_result.raw_output
                    }
                device_uuid = uuid_result.result_data
                target_device.setUuid(device_uuid)
            if not device_uuid:
                error_msg = "设备UUID为空"
                logging.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg,
                    'details': ''
                }

            logging.info(f"获取到设备UUID: {device_uuid}")

            # 步骤2: 使用激活盒子签名
            if progress_callback:
                progress_callback("正在使用激活盒子签名...")

            sign_result = cube.sign_uuid(device_uuid)
            if not sign_result.success:
                error_msg = f"激活盒子签名失败: {sign_result.error_message}"
                logging.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg,
                    'details': sign_result.raw_output
                }

            signature = sign_result.result_data
            if not signature:
                error_msg = "签名结果为空"
                logging.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg,
                    'details': sign_result.raw_output
                }

            logging.info(f"获取到签名: {signature}")

            # 步骤3: 激活设备
            if progress_callback:
                progress_callback("正在激活设备...")

            activate_result = target_device.activate(signature)
            if not activate_result.success:
                error_msg = f"设备激活失败: {activate_result.error_message}"
                logging.error(error_msg)
                self._mark_activation_failed_and_block(
                    serial=device_serial,
                    uuid=device_uuid,
                    signature=signature,
                    message=error_msg,
                    details=activate_result.raw_output,
                )
                return {
                    'success': False,
                    'message': error_msg,
                    'details': activate_result.raw_output
                }

            logging.info(f"设备激活成功: {device_serial}")
            try:
                self.device_monitor.refresh_all_cube()
            except Exception as refresh_error:
                # 刷新仅用于尽快更新Cube快照，不应影响激活主流程结果
                logging.warning(f"激活后刷新Cube失败: {refresh_error}")

            # 步骤4: 验证激活状态
            if progress_callback:
                progress_callback("正在验证激活状态...")

            if target_device.getDetectionMethod().strip().lower() == "adb":
                state_result = self.adb_manager.get_device_state(device_serial)
                verify_success = state_result.success and state_result.result_data == "Authorized"
                verify_error = state_result.error_message
                verify_output = state_result.raw_output
            else:
                verify_success = (target_device.getStatus() or "").strip().lower() == "authorized"
                verify_error = ""
                verify_output = target_device.getStatus()

            if verify_success:
                success_msg = f"设备激活成功: {device_serial}"
                logging.info(success_msg)
                return {
                    'success': True,
                    'message': success_msg,
                    'details': f"UUID: {device_uuid}\n签名: {signature}\n状态: 已激活"
                }
            else:
                error_msg = f"设备激活可能失败，状态验证异常: {verify_error}"
                logging.warning(error_msg)
                self._mark_activation_failed_and_block(
                    serial=device_serial,
                    uuid=device_uuid,
                    signature=signature,
                    message=error_msg,
                    details=verify_output,
                )
                return {
                    'success': False,
                    'message': error_msg,
                    'details': verify_output
                }

        except Exception as e:
            error_msg = f"激活过程发生异常: {str(e)}"
            logging.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'details': str(e)
            }

    def check_device_authentication_status(self, device_serial: str) -> str:
        """检查设备激活状态"""
        try:
            result = self.adb_manager.get_device_state(device_serial)
            if result.success:
                return result.result_data
            else:
                return "Unknown"
        except Exception as e:
            logging.error(f"检查设备激活状态失败: {e}")
            return "Error"

    def get_available_authenticators(self) -> List[str]:
        """获取可用的激活盒子列表"""
        serials = set(self.device_monitor.authenticators.keys())
        with self._simulated_lock:
            serials.update(self._simulated_cubes.keys())
        return sorted(serials)

    def is_simulated_cube(self, serial: str) -> bool:
        with self._simulated_lock:
            return str(serial or "") in self._simulated_cubes

    def get_simulated_cube_infos(self) -> Dict[str, AuthenticatorInfo]:
        with self._simulated_lock:
            return {serial: cube.to_authenticator_info() for serial, cube in self._simulated_cubes.items()}

    def _allocate_simulated_cube_serial(self) -> str:
        max_attempts = 10_000
        attempts = 0
        while attempts < max_attempts:
            attempts += 1
            self._simulated_cube_counter += 1
            serial = f"SIM-CUBE-{self._simulated_cube_counter:04d}"
            if serial not in self._simulated_cubes:
                return serial
        raise RuntimeError("自动分配模拟Cube序列号失败: 可用序列号已耗尽")

    def create_simulated_cube(
        self,
        expired_date: str,
        counter: int,
        private_key_path: str,
        cube_id: str,
        oem_id: str,
        persist_path: str,
        serial_id: str = "",
    ) -> str:
        if not self.is_simulation_enabled():
            raise RuntimeError("模拟功能未启用")
        if not private_key_path or not os.path.exists(private_key_path):
            raise ValueError("P256私钥路径无效")
        if not persist_path:
            raise ValueError("持久化路径不能为空")
        with self._simulated_lock:
            serial = str(serial_id or "").strip() or self._allocate_simulated_cube_serial()
            if serial in self._simulated_cubes:
                raise ValueError(f"模拟Cube序列号已存在: {serial}")
            self._simulated_cubes[serial] = ICube.CreateSimulation(
                serial=serial,
                cube_id=str(cube_id or serial),
                oem_id=str(oem_id or ""),
                expired_date=str(expired_date or ""),
                counter=max(int(counter), 0),
                private_key_path=str(private_key_path),
                persist_path=str(persist_path),
            )
        return serial

    def load_simulated_cube(self, persist_path: str, private_key_path: str, serial_id: str = "") -> str:
        if not self.is_simulation_enabled():
            raise RuntimeError("模拟功能未启用")
        if not persist_path or not os.path.exists(persist_path):
            raise ValueError("Cube持久化路径无效")
        if not private_key_path or not os.path.exists(private_key_path):
            raise ValueError("P256私钥路径无效")
        with self._simulated_lock:
            serial_override = str(serial_id or "").strip()
            cube = ICube.LoadSimulation(
                persist_path=persist_path,
                private_key_path=private_key_path,
                serial_override=serial_override,
            )
            serial = cube.get_serial()
            if serial in self._simulated_cubes:
                raise ValueError(f"模拟Cube序列号已存在: {serial}")
            self._simulated_cubes[serial] = cube
        return serial

    def perform_cube_operation(self, operation: str, serial: str, payload: str):
        cube = self._resolve_cube(serial)
        if operation == 'lock':
            return cube.lock(payload)
        if operation == 'unlock':
            return cube.unlock(payload)
        if operation == 'activate':
            return cube.activate(payload)
        if operation == 'config':
            return cube.config(payload)
        raise ValueError(f"Unsupported cube operation: {operation}")

    def _resolve_cube(self, serial: str) -> ICube:
        serial = str(serial or "").strip()
        with self._simulated_lock:
            if serial in self._simulated_cubes:
                return self._simulated_cubes[serial]
        known_authenticators = getattr(self.device_monitor, "authenticators", {}) or {}
        if serial not in known_authenticators:
            raise ValueError(f"未找到Cube: {serial}")
        return RealCube(serial=serial, adb_manager=self.adb_manager)

    @staticmethod
    def _normalize_status(value: str) -> str:
        return str(value or "").strip().lower()

    def is_device_queued_for_auto_activation(self, serial: str) -> bool:
        serial = str(serial or "")
        with self._queue_lock:
            return serial in self._queued_serials or serial in self._in_progress_serials

    def is_device_auto_activation_completed(self, serial: str) -> bool:
        serial = str(serial or "")
        with self._queue_lock:
            return serial in self._auto_activation_completed_serials

    def get_unauthorized_devices(self) -> List[DeviceInfo]:
        """获取未激活设备列表"""
        unauthorized_devices = []
        for device in self.device_monitor.get_ready_devices():
            if (device.status or "").strip().lower() == "unauthorized" and device.uuid:
                unauthorized_devices.append(device)
        return unauthorized_devices
