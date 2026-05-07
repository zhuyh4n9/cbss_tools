"""
激活管理器
负责处理设备激活流程
"""
import logging
import queue
import secrets
import threading
import time
from typing import List, Optional, Callable, Dict
from .adb_manager import ADBManager, DeviceInfo
from .device_monitor import DeviceMonitor
from .build_options import ENABLE_SIMULATED_DEVICE, SIMULATED_DEVICE_STATUS_OPTIONS
from .target_device import AC8267Device, ITargetDevice, SimulatorDevice


class AuthenticationManager:
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
        self._queue_lock = threading.Lock()
        self._worker_running = False
        self._worker_thread = None
        self._stop_event = threading.Event()
        self._simulated_devices: Dict[str, SimulatorDevice] = {}
        self._simulated_counter = 0
        self._simulated_lock = threading.Lock()

        # 始终注册回调，是否入队由开关控制
        self.device_monitor.device_parser.add_callback('unauthorized_ready', self._on_unauthorized_ready)

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
                self._queued_serials.add(serial)

            self._activate_queue.put(serial)
            logging.info(f"未授权设备已加入自动授权队列: {serial}")
        except Exception as e:
            logging.error(f"提交自动授权队列失败: {e}")

    def _pick_authenticator(self) -> Optional[str]:
        authenticators = self.get_available_authenticators()
        if not authenticators:
            return None
        # 固定顺序选择，避免来回切换
        return sorted(authenticators)[0]

    def _is_device_still_unauthorized(self, serial: str) -> bool:
        try:
            device = self.device_monitor.get_device_by_serial(serial)
            if not device and self.is_simulated_device(serial):
                with self._simulated_lock:
                    simulated = self._simulated_devices.get(str(serial))
                    device = simulated.to_device_info() if simulated else None
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

    def is_simulated_device_enabled(self) -> bool:
        """是否启用模拟设备功能（编译/打包选项）"""
        return ENABLE_SIMULATED_DEVICE

    def is_simulated_device(self, serial: str) -> bool:
        serial = str(serial or "")
        with self._simulated_lock:
            return serial in self._simulated_devices

    def get_simulated_devices(self) -> List[DeviceInfo]:
        with self._simulated_lock:
            return [device.to_device_info() for device in self._simulated_devices.values()]

    def add_simulated_device(self, status: str) -> DeviceInfo:
        if not self.is_simulated_device_enabled():
            raise RuntimeError("模拟设备功能未启用")

        status_input = (status or "").strip().lower()
        status_map = {item.lower(): item for item in SIMULATED_DEVICE_STATUS_OPTIONS}
        normalized_status = status_map.get(status_input, "Unauthorized")
        if status_input and status_input not in status_map:
            logging.warning(f"收到未知模拟设备状态，已回退为Unauthorized: {status}")

        with self._simulated_lock:
            self._simulated_counter += 1
            serial = f"SIM-{self._simulated_counter:04d}"
            device = ITargetDevice.CreateSimulation(
                status=normalized_status,
                serial_number=serial,
                uuid=secrets.token_hex(32)
            )
            if not isinstance(device, SimulatorDevice):
                raise RuntimeError("模拟设备创建失败")
            self._simulated_devices[serial] = device

        if self._auto_activation_enabled and (device.getStatus() or "").strip().lower() == "unauthorized" and device.getUuid():
            self._on_unauthorized_ready(device.to_device_info())

        return device.to_device_info()

    def _activate_simulated_device(self, serial: str) -> dict:
        with self._simulated_lock:
            device = self._simulated_devices.get(str(serial))
            if not device:
                return {
                    'success': False,
                    'message': f'模拟设备不存在: {serial}',
                    'details': ''
                }

            status = (device.getStatus() or "").strip().lower()
            if status != "unauthorized":
                return {
                    'success': False,
                    'message': f'模拟设备状态非Unauthorized，无法激活: {device.getStatus()}',
                    'details': ''
                }

            activate_result = device.activate("simulated-signature")
            if not activate_result.success:
                return {
                    'success': False,
                    'message': activate_result.error_message or '模拟设备激活失败',
                    'details': activate_result.raw_output
                }

        return {
            'success': True,
            'message': f'设备激活成功: {serial}',
            'details': '模拟设备已从Unauthorized切换为Authorized'
        }

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

            if self.is_simulated_device(device_serial):
                if progress_callback:
                    progress_callback("正在准备模拟设备认证...")

                with self._simulated_lock:
                    simulated_device = self._simulated_devices.get(str(device_serial))

                if not simulated_device:
                    return {
                        'success': False,
                        'message': f'模拟设备不存在: {device_serial}',
                        'details': ''
                    }

                device_uuid = (simulated_device.getUuid() or "").strip()
                if not device_uuid:
                    return {
                        'success': False,
                        'message': "设备UUID为空",
                        'details': ''
                    }

                if progress_callback:
                    progress_callback("正在使用激活盒子签名...")

                sign_result = self.adb_manager.authenticator_sign(authenticator_serial, device_uuid)
                if not sign_result.success:
                    error_msg = f"激活盒子签名失败: {sign_result.error_message}"
                    logging.error(error_msg)
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': sign_result.raw_output
                    }

                signature = (sign_result.result_data or "").strip()
                if not signature:
                    error_msg = "签名结果为空"
                    logging.error(error_msg)
                    return {
                        'success': False,
                        'message': error_msg,
                        'details': sign_result.raw_output
                    }

                if progress_callback:
                    progress_callback("正在激活模拟设备...")

                simulated_activate_result = self._activate_simulated_device(device_serial)
                if not simulated_activate_result.get('success'):
                    return simulated_activate_result

                success_msg = f"设备激活成功: {device_serial}"
                return {
                    'success': True,
                    'message': success_msg,
                    'details': f"UUID: {device_uuid}\n签名: {signature}\n状态: 已激活(模拟设备)"
                }

            # 步骤1: 获取设备UUID
            if progress_callback:
                progress_callback("正在获取设备UUID...")

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
            if not device_uuid:
                error_msg = "设备UUID为空"
                logging.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg,
                    'details': uuid_result.raw_output
                }

            logging.info(f"获取到设备UUID: {device_uuid}")

            # 步骤2: 使用激活盒子签名
            if progress_callback:
                progress_callback("正在使用激活盒子签名...")

            sign_result = self.adb_manager.authenticator_sign(authenticator_serial, device_uuid)
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

            target_device = ITargetDevice.CreateAdbDevice(device_serial, self.adb_manager)
            if not isinstance(target_device, AC8267Device):
                target_device = AC8267Device(
                    serial_number=device_serial,
                    adb_manager=self.adb_manager,
                    uuid=device_uuid,
                    status="Unknown"
                )
            if not target_device.getUuid():
                target_device.setUuid(device_uuid)
            activate_result = target_device.activate(signature)
            if not activate_result.success:
                error_msg = f"设备激活失败: {activate_result.error_message}"
                logging.error(error_msg)
                return {
                    'success': False,
                    'message': error_msg,
                    'details': activate_result.raw_output
                }

            logging.info(f"设备激活成功: {device_serial}")

            # 步骤4: 验证激活状态
            if progress_callback:
                progress_callback("正在验证激活状态...")

            state_result = self.adb_manager.get_device_state(device_serial)
            if state_result.success and state_result.result_data == "Authorized":
                success_msg = f"设备激活成功: {device_serial}"
                logging.info(success_msg)
                return {
                    'success': True,
                    'message': success_msg,
                    'details': f"UUID: {device_uuid}\n签名: {signature}\n状态: 已激活"
                }
            else:
                error_msg = f"设备激活可能失败，状态验证异常: {state_result.error_message}"
                logging.warning(error_msg)
                return {
                    'success': False,
                    'message': error_msg,
                    'details': state_result.raw_output
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
        return list(self.device_monitor.authenticators.keys())

    def get_unauthorized_devices(self) -> List[DeviceInfo]:
        """获取未激活设备列表"""
        unauthorized_devices = []
        for device in self.device_monitor.get_ready_devices():
            if (device.status or "").strip().lower() == "unauthorized" and device.uuid:
                unauthorized_devices.append(device)
        for device in self.get_simulated_devices():
            if (device.status or "").strip().lower() == "unauthorized" and device.uuid:
                unauthorized_devices.append(device)
        return unauthorized_devices
