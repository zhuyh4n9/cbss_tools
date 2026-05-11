"""
激活管理器
负责处理设备激活流程
"""
import logging
import queue
import threading
import time
from typing import List, Optional, Callable
from .adb_manager import ADBManager, DeviceInfo, AuthenticatorInfo
from .device_monitor import DeviceMonitor
from .target_device import ITargetDevice
from .cube import ICube, RealCube


class AuthenticationManager:
    _READY_TIME_STATUS = "ready"

    def __init__(self, adb_manager: ADBManager, device_monitor: DeviceMonitor):
        self.adb_manager = adb_manager
        self.device_monitor = device_monitor
        self._log_manager = None  # 由 main_gui 设置

        self._authentication_lock = threading.Lock()
        self._is_authenticating = False

        # 自动授权功能
        self._auto_activation_enabled = self.device_monitor.config.getboolean('General', 'auto_activation_enabled', False)
        self._activate_queue: queue.Queue[Optional[str]] = queue.Queue()
        self._queued_serials = set()
        self._in_progress_serials = set()
        self._auto_activation_completed_serials = set()
        self._queue_lock = threading.Lock()
        self._worker_running = False
        self._worker_thread = None
        self._stop_event = threading.Event()

        # 始终注册回调，是否入队由开关控制（parser的ADB设备 + device_monitor的模拟设备）
        self.device_monitor.device_parser.add_callback('unauthorized_ready', self._on_unauthorized_ready)
        self.device_monitor.add_callback('unauthorized_ready', self._on_unauthorized_ready)

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
            serial = str(device.serial)
            if not serial:
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

    def _pick_authenticator(self) -> Optional[str]:
        ready_authenticators = []
        for serial in self.get_available_authenticators():
            auth_info = self.device_monitor.get_authenticator_by_serial(serial)
            if auth_info is None:
                # 可能是模拟Cube，没有ADB snapshot但time_status默认Ready
                ready_authenticators.append(serial)
                continue
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

            serial = str(serial)
            with self._queue_lock:
                self._queued_serials.discard(serial)

            # 设备状态变化后无需处理
            if not self._is_device_still_unauthorized(serial):
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
                self._in_progress_serials.add(serial)

            try:
                result = self._run_authentication(serial, authenticator_serial)
                if result.get('success'):
                    logging.info(f"自动授权成功: {serial}")
                    with self._queue_lock:
                        self._auto_activation_completed_serials.add(serial)
                    # 立即更新target_devices状态，不等parser异步刷新
                    self.device_monitor.update_device_status(serial, "Authorized")
                else:
                    logging.warning(f"自动授权失败: {serial}, {result.get('message', '')}")

                # 自动授权后通知parser重新获取设备状态（异步校验，保留当前状态不产生重复入队）
                if self._worker_running and not self._stop_event.is_set():
                    self.device_monitor.refresh_all_cube()
                    self.device_monitor.reparse_device(serial)
            except Exception as e:
                logging.error(f"自动授权执行异常: {serial}, {e}")
            finally:
                with self._queue_lock:
                    self._in_progress_serials.discard(serial)

    def is_authenticating(self) -> bool:
        """检查是否正在执行激活"""
        return self._is_authenticating

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
        """执行单个设备的激活流程（lock→check→sign→log→double check→activate）"""
        target = None
        cube = None
        cube_id = str(authenticator_serial or "")
        device_uuid = ""
        signature = ""
        log_mgr = self._log_manager

        try:
            logging.info(f"开始激活设备: {device_serial}")

            cube = self._resolve_cube(authenticator_serial)
            target = self._resolve_target_device(device_serial)
            if target is None:
                return {
                    'success': False,
                    'message': f'设备不存在: {device_serial}',
                    'details': ''
                }

            # 检查AuthorizationFailure状态
            if target.getStatus().lower() == "authorizationfailure":
                return {
                    'success': False,
                    'message': f'设备 {device_serial} 处于AuthorizationFailure状态，无法激活',
                    'details': ''
                }

            # 步骤1: 锁定设备
            if progress_callback:
                progress_callback("正在锁定设备...")
            if not target.lock():
                return {
                    'success': False,
                    'message': f'无法锁定设备: {device_serial}',
                    'details': ''
                }

            try:
                # 步骤2: 检查设备状态
                if progress_callback:
                    progress_callback("正在检查设备状态...")
                device_uuid = (target.getUuid() or "").strip()
                if not device_uuid:
                    target.markDirty()
                    return {
                        'success': False,
                        'message': "设备UUID为空",
                        'details': ''
                    }
                status = target.getStatus().strip().lower()
                if status != "unauthorized":
                    target.markDirty()
                    return {
                        'success': False,
                        'message': f'设备状态不正确: {target.getStatus()}',
                        'details': ''
                    }

                logging.info(f"获取到设备UUID: {device_uuid}")

                # 步骤3: 使用激活盒子签名
                if progress_callback:
                    progress_callback("正在使用激活盒子签名...")

                sign_result = cube.sign_uuid(device_uuid)
                if not sign_result.success:
                    error_msg = f"激活盒子签名失败: {sign_result.error_message}"
                    logging.error(error_msg)
                    # 记录失败日志
                    self._log_auth_result(log_mgr, False, device_serial, device_uuid, "", cube_id, error_msg, cube)
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': sign_result.raw_output
                    }

                signature = (sign_result.result_data or "").strip()
                if not signature:
                    error_msg = "签名结果为空"
                    logging.error(error_msg)
                    self._log_auth_result(log_mgr, False, device_serial, device_uuid, "", cube_id, error_msg, cube)
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': sign_result.raw_output
                    }

                logging.info(f"获取到签名: {signature}")

                # 步骤4: 记录到 all/ (签名成功后先记录)
                self._log_auth_result(log_mgr, True, device_serial, device_uuid, signature, cube_id, "", cube)

                # 步骤5: double check 状态
                if progress_callback:
                    progress_callback("正在二次确认设备状态...")
                double_check_status = self.device_monitor.get_device_auth_status(device_serial)
                if double_check_status.strip().lower() != "unauthorized":
                    error_msg = f"设备状态已变化: {double_check_status}"
                    self._log_auth_result(log_mgr, False, device_serial, device_uuid, signature, cube_id, error_msg, cube)
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': ''
                    }

                # 步骤6: 激活设备
                if progress_callback:
                    progress_callback("正在激活设备...")

                activate_result = target.activate(signature)
                if not activate_result.success:
                    error_msg = f"设备激活失败: {activate_result.error_message}"
                    logging.error(error_msg)
                    self._log_auth_result(log_mgr, False, device_serial, device_uuid, signature, cube_id, error_msg, cube)
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': activate_result.raw_output
                    }

                logging.info(f"设备激活成功: {device_serial}")
                try:
                    self.device_monitor.refresh_all_cube()
                except Exception as refresh_error:
                    logging.warning(f"激活后刷新Cube失败: {refresh_error}")

                success_msg = f"设备激活成功: {device_serial}"
                is_sim = target.is_simulation if hasattr(target, 'is_simulation') else False
                return {
                    'success': True,
                    'message': success_msg,
                    'details': f"UUID: {device_uuid}\n签名: {signature}\n状态: 已激活{' (模拟设备)' if is_sim else ''}"
                }

            finally:
                # 确保一定unlock
                target.unlock()

        except Exception as e:
            error_msg = f"激活过程发生异常: {str(e)}"
            logging.error(error_msg)
            if cube is not None:
                self._log_auth_result(log_mgr, False, device_serial, device_uuid, signature, cube_id, error_msg, cube)
            # 确保异常时也unlock
            if target is not None:
                try:
                    target.unlock()
                except Exception:
                    pass
            return {
                'success': False,
                'message': error_msg,
                'details': str(e)
            }

    @staticmethod
    def _log_auth_result(log_mgr, success: bool, device_serial: str, uuid: str,
                         signature: str, cube_id: str, error_reason: str, cube: ICube) -> None:
        """记录授权结果到日志"""
        if log_mgr is None:
            return
        try:
            if not success and error_reason:
                cube_info = cube.to_authenticator_info()
                cube_status = str(cube_info.device_status)
                cube_expire = str(cube_info.expired_date or "")
                log_mgr.log_authorization_failure(
                    device_serial=device_serial, uuid=uuid, signature=signature,
                    cube_id=cube_id, error_reason=error_reason,
                    cube_status=cube_status, cube_expire=cube_expire,
                )
            else:
                log_mgr.log_authorization(
                    success=success, device_serial=device_serial, uuid=uuid,
                    signature=signature, cube_id=cube_id, error_reason=error_reason,
                )
        except Exception:
            pass

    def _resolve_target_device(self, serial: str) -> Optional[ITargetDevice]:
        """根据serial解析ITargetDevice（委托device_monitor统一处理）"""
        return self.device_monitor.get_target_device(serial)

    def check_device_authentication_status(self, device_serial: str) -> str:
        """检查设备激活状态（委托device_monitor统一处理）"""
        return self.device_monitor.get_device_auth_status(device_serial)

    def get_available_authenticators(self) -> List[str]:
        """获取可用的激活盒子列表（统一从DeviceMonitor获取）"""
        return sorted(self.device_monitor.authenticators.keys())

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
        if self.device_monitor.is_simulated_cube(serial):
            return self.device_monitor._simulated_cubes[serial]
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
        """获取未激活设备列表（包括真实设备和模拟设备）"""
        unauthorized_devices = []
        seen_serials = set()
        for device in self.device_monitor.target_devices:
            serial = str(device.serial)
            if serial in seen_serials:
                continue
            seen_serials.add(serial)
            if (device.status or "").strip().lower() == "unauthorized" and device.uuid:
                unauthorized_devices.append(device)
        return unauthorized_devices
