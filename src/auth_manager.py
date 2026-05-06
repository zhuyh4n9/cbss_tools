"""
激活管理器
负责处理设备激活流程
"""
import logging
import queue
import threading
import time
from typing import List, Optional, Callable
from .adb_manager import ADBManager, DeviceInfo
from .device_monitor import DeviceMonitor


class AuthenticationManager:
    def __init__(self, adb_manager: ADBManager, device_monitor: DeviceMonitor):
        self.adb_manager = adb_manager
        self.device_monitor = device_monitor

        self._authentication_lock = threading.Lock()
        self._is_authenticating = False

        # 自动授权功能
        self._auto_activation_enabled = self.device_monitor.config.getboolean('General', 'auto_activation_enabled', False)
        self._activate_queue: queue.Queue[str] = queue.Queue()
        self._queued_serials = set()
        self._in_progress_serials = set()
        self._queue_lock = threading.Lock()
        self._worker_running = False
        self._worker_thread = None

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

    def stop(self):
        """停止后台线程"""
        if not self._worker_running:
            return
        self._worker_running = False
        # 发送哨兵值，快速唤醒队列阻塞
        self._activate_queue.put(None)
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)

    def _start_activate_worker(self):
        if self._worker_running:
            return
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
            if not device:
                return False
            status = (device.status or "").strip().lower()
            return status == "unauthorized" and bool(device.uuid)
        except Exception:
            return False

    def _activate_worker_loop(self):
        while self._worker_running:
            serial = None
            try:
                serial = self._activate_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # 停止哨兵
            if serial is None:
                continue

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

                # 自动授权后自动刷新Cube和Target Device
                self.device_monitor.refresh_all_cube()
                self.device_monitor.refresh_all_device()
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
        """执行单个设备的激活流程"""
        try:
            logging.info(f"开始激活设备: {device_serial}")

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

            activate_result = self.adb_manager.activate_device(device_serial, signature)
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
        return unauthorized_devices
