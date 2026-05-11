"""
设备解析器
负责设备类型识别与目标设备异步解析，维护await/ready双队列
"""

import copy
import logging
import threading
import time
from typing import Callable, Dict, List

from .adb_manager import ADBManager, DeviceInfo
from .device_classification_strategy import DeviceClassificationStrategy
from .cube_manager import CubeManager
from .target_device import TargetDeviceAbstract, UnknownAdbDevice, UnknownDevice


class DeviceParser:
    def __init__(self, adb_manager: ADBManager):
        self.adb_manager = adb_manager

        self._await_queue: Dict[str, TargetDeviceAbstract] = {}
        self._ready_queue: Dict[str, TargetDeviceAbstract] = {}
        self._base_devices: Dict[str, TargetDeviceAbstract] = {}
        self._classify_queue: List[str] = []
        self._order: List[str] = []
        self._classification_strategy = DeviceClassificationStrategy(self.adb_manager)

        self.cube_manager = CubeManager(self.adb_manager)
        self.cube_manager.add_callback('authenticator_update', self._on_cube_update)
        self.cube_manager.add_callback('error', lambda err: self._notify_callbacks('error', err))

        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._wake_event = threading.Event()

        self._callbacks = {
            'device_update': [],
            'authenticator_update': [],
            'authenticator_serials_update': [],
            'unauthorized_ready': [],
            'error': [],
        }

    def _on_cube_update(self, cubes):
        self._notify_callbacks('authenticator_update', cubes)
        self._notify_callbacks('authenticator_serials_update', list(cubes.keys()))

    def kick(self):
        """遍历全部设备，寻找dirty状态设备，执行refreshDeviceMeta"""
        with self._lock:
            dirty_serials = []
            for serial, dev in self._ready_queue.items():
                if dev.isDirty():
                    dirty_serials.append(serial)
            for serial, dev in self._await_queue.items():
                if dev.isDirty():
                    dirty_serials.append(serial)

        for serial in dirty_serials:
            with self._lock:
                dev = self._ready_queue.get(serial) or self._await_queue.get(serial)
            if dev is None:
                continue
            try:
                logging.info(f"refreshDeviceMeta 开始 [{serial}]")
                dev.refreshDeviceMeta()
                logging.info(f"refreshDeviceMeta 完成 [{serial}], status={dev.getStatus()}, uuid={dev.getUuid()[:16] if dev.getUuid() else ''}...")
            except Exception as e:
                logging.error(f"refreshDeviceMeta 失败 [{serial}]: {e}")

        if dirty_serials:
            self._notify_callbacks('device_update', self.get_devices())
            for serial in dirty_serials:
                with self._lock:
                    dev = self._ready_queue.get(serial)
                if dev is not None and not dev.isDirty():
                    if dev.getStatus().strip().lower() == "unauthorized" and dev.getUuid():
                        if not getattr(dev, '_submitted', False):
                            dev._submitted = True
                            self._notify_callbacks('unauthorized_ready', copy.deepcopy(dev.to_device_info()))

    def start(self):
        if self._running:
            return
        self.cube_manager.start()
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logging.info("DeviceParser 已启动")

    def stop(self, join_timeout: float = 2.0):
        self._running = False
        self._wake_event.set()
        if self._thread:
            self._thread.join(timeout=max(float(join_timeout or 0), 0.0))
        self.cube_manager.stop(join_timeout=join_timeout)
        logging.info("DeviceParser 已停止")

    def add_callback(self, event_type: str, callback: Callable):
        if event_type in self._callbacks:
            self._callbacks[event_type].append(callback)

    def _notify_callbacks(self, event_type: str, data=None):
        for callback in self._callbacks.get(event_type, []):
            try:
                callback(data)
            except Exception as e:
                logging.error(f"DeviceParser 回调执行失败: {e}")

    @staticmethod
    def _log_device_event(event: str, device_info: DeviceInfo):
        logging.info(
            "设备事件: %s, serial=%s, status=%s, device_type=%s, usb_port=%s, detection=%s",
            event,
            device_info.serial,
            device_info.status,
            device_info.device_type,
            device_info.usb_port,
            device_info.detection_method
        )

    def _to_target_device(self, device: DeviceInfo) -> TargetDeviceAbstract:
        detection_method = (device.detection_method or "Unknown").strip() or "Unknown"
        serial = str(device.serial)
        usb_port = str(device.usb_port or "")
        if detection_method.lower() == "adb":
            return UnknownAdbDevice(
                serial_number=serial,
                adb_manager=self.adb_manager,
                usb_port=usb_port,
                status=device.status or "Unknown",
            )
        if device.is_simulation:
            from .target_device import ITargetDevice
            from .device_source import SimulatorDeviceDetector
            failure_flag = SimulatorDeviceDetector._sim_failure_flags.get(serial, False)
            return ITargetDevice.CreateSimulation(
                status=device.status or "Unauthorized",
                serial_number=serial,
                uuid=device.uuid,
                simulate_activate_failure=failure_flag,
            )
        return UnknownDevice(
            detection_method=detection_method,
            serial_number=serial,
            is_simulation=bool(device.is_simulation),
            usb_port=usb_port,
        )

    def _make_await_device(self, device: TargetDeviceAbstract) -> TargetDeviceAbstract:
        d = copy.deepcopy(device)
        d.setUuid("")
        d.status = "Checking..."
        return d

    def _make_unknown_device(self, device: TargetDeviceAbstract) -> TargetDeviceAbstract:
        detection_method = device.getDetectionMethod()
        serial = device.getSerialNumber()
        usb_port = device.getConnectedUsbPort()
        if detection_method.lower() == "adb":
            return UnknownAdbDevice(serial_number=serial, adb_manager=self.adb_manager, usb_port=usb_port, status="Unknown")
        return UnknownDevice(
            detection_method=detection_method,
            serial_number=serial,
            is_simulation=device.is_simulation,
            usb_port=usb_port,
        )

    def add_device(self, device: DeviceInfo):
        """向分类队列添加设备（device_monitor调用）"""
        serial = str(device.serial)
        with self._lock:
            self._base_devices[serial] = self._to_target_device(copy.deepcopy(device))
            if serial not in self._order:
                self._order.append(serial)
            if serial not in self._classify_queue and not self.cube_manager.has_cube(serial) and serial not in self._await_queue and serial not in self._ready_queue:
                self._classify_queue.append(serial)

        self._wake_event.set()

    def sync_connected_devices(self, added_devices: List[DeviceInfo] = None,
                               removed_serials: List[str] = None):
        """同步设备增删：device_monitor直接告知新增和移除"""
        added_devices = added_devices or []
        removed_serials = removed_serials or []

        with self._lock:
            for serial in removed_serials:
                removed_info = self._base_devices.get(serial)
                if removed_info:
                    try:
                        self._log_device_event("removed", removed_info.to_device_info())
                    except Exception as log_error:
                        logging.warning(f"记录设备移除日志失败 [{serial}]: {log_error}")
                self._base_devices.pop(serial, None)
                self._await_queue.pop(serial, None)
                self._ready_queue.pop(serial, None)
                self._classify_queue = [s for s in self._classify_queue if s != serial]
                self._order = [s for s in self._order if s != serial]
                self.cube_manager.remove_cube(serial)

            for device in added_devices:
                serial = str(device.serial)
                target = self._to_target_device(copy.deepcopy(device))
                try:
                    self._log_device_event("added", target.to_device_info())
                except Exception as log_error:
                    logging.warning(f"记录新设备日志失败 [{serial}]: {log_error}")
                self._base_devices[serial] = target
                if serial not in self._order:
                    self._order.append(serial)
                if serial not in self._classify_queue and not self.cube_manager.has_cube(serial):
                    self._classify_queue.append(serial)

        if added_devices or removed_serials:
            self._notify_callbacks('device_update', self.get_devices())
            self._wake_event.set()

    def remove_device(self, serial: str):
        """从await/ready队列移除设备（device_monitor调用）"""
        serial = str(serial)
        with self._lock:
            self._base_devices.pop(serial, None)
            in_target = serial in self._await_queue or serial in self._ready_queue
            self._await_queue.pop(serial, None)
            self._ready_queue.pop(serial, None)
            self._classify_queue = [s for s in self._classify_queue if s != serial]
            self._order = [s for s in self._order if s != serial]

        if not in_target:
            self.cube_manager.remove_cube(serial)

        self._notify_callbacks('device_update', self.get_devices())

    def refresh_device(self, serial: str):
        """刷新单个设备：ready -> await（清空UUID/状态，用于用户手动刷新）"""
        serial = str(serial)
        forwarded_to_cube = False
        with self._lock:
            if serial in self._ready_queue:
                dev = self._ready_queue.pop(serial)
                self._await_queue[serial] = self._make_await_device(dev)
            elif serial not in self._await_queue:
                forwarded_to_cube = True

        if forwarded_to_cube:
            self.cube_manager.refresh_cube(serial)

        self._notify_callbacks('device_update', self.get_devices())
        self._wake_event.set()

    def reparse_device(self, serial: str):
        """激活后重新获取设备状态：ready -> await（保留UUID/状态，避免UI闪烁和重复入队）"""
        serial = str(serial)
        with self._lock:
            if serial in self._ready_queue:
                dev = self._ready_queue.pop(serial)
                # 保留当前UUID和状态，仅放入await队列等待解析器重新获取
                preserved = copy.deepcopy(dev)
                self._await_queue[serial] = preserved

        self._notify_callbacks('device_update', self.get_devices())
        self._wake_event.set()

    def refresh_all_device(self):
        """刷新全部设备：ready全部移入await"""
        with self._lock:
            for serial, dev in list(self._ready_queue.items()):
                self._await_queue[serial] = self._make_await_device(dev)
            self._ready_queue.clear()

        self._notify_callbacks('device_update', self.get_devices())
        self._wake_event.set()

    def refresh_all_cube(self):
        """刷新全部Cube信息（不刷新target设备）"""
        self.cube_manager.refresh_all_cube()
        self._wake_event.set()

    def get_devices(self) -> List[DeviceInfo]:
        """获取当前显示设备（await+ready，保持顺序）"""
        with self._lock:
            out = []
            for serial in self._order:
                if serial in self._ready_queue:
                    dev = self._ready_queue[serial].to_device_info()
                    if dev.device_type in ("target_device", "unknown"):
                        out.append(copy.deepcopy(dev))
                elif serial in self._await_queue:
                    dev = self._await_queue[serial].to_device_info()
                    if dev.device_type in ("target_device", "unknown"):
                        out.append(copy.deepcopy(dev))
            return out

    def get_ready_devices(self) -> List[DeviceInfo]:
        with self._lock:
            return [copy.deepcopy(self._ready_queue[s].to_device_info()) for s in self._order if s in self._ready_queue]

    def get_authenticator_serials(self) -> List[str]:
        return self.cube_manager.get_cube_serials()

    def _next_classify_serial(self):
        with self._lock:
            if self._classify_queue:
                return self._classify_queue.pop(0)
        return None

    def _next_await_serial(self):
        with self._lock:
            for serial in self._order:
                if serial in self._await_queue:
                    return serial
        return None

    def _worker_loop(self):
        while self._running:
            try:
                classify_serial = self._next_classify_serial()
                if classify_serial:
                    known_cube = self.cube_manager.has_cube(classify_serial)

                    with self._lock:
                        base = self._base_devices.get(classify_serial)
                    if not base:
                        continue

                    decision = self._classification_strategy.classify_device(classify_serial, base, known_cube, self.kick)

                    with self._lock:
                        base = self._base_devices.get(classify_serial)
                        if not base:
                            continue
                        if known_cube:
                            self._await_queue.pop(classify_serial, None)
                            self._ready_queue.pop(classify_serial, None)
                        elif decision.ready_device is not None and not isinstance(decision.ready_device, UnknownAdbDevice):
                            self._await_queue.pop(classify_serial, None)
                            self._ready_queue[classify_serial] = decision.ready_device
                        else:
                            if decision.should_add_cube:
                                self._await_queue.pop(classify_serial, None)
                                self._ready_queue.pop(classify_serial, None)
                            else:
                                if decision.should_mark_unknown:
                                    self._base_devices[classify_serial] = self._make_unknown_device(base)
                                self._await_queue.pop(classify_serial, None)
                                self._ready_queue.pop(classify_serial, None)

                    if decision.should_add_cube:
                        self.cube_manager.add_cube(classify_serial)

                    self._notify_callbacks('device_update', self.get_devices())
                    # 设备已在_ready_queue中，此时markDirty触发kick→refreshDeviceMeta→unauthorized_ready
                    if decision.ready_device is not None:
                        decision.ready_device.markDirty(self.kick)
                    continue

                serial = self._next_await_serial()
                if not serial:
                    self._wake_event.wait(timeout=0.5)
                    self._wake_event.clear()
                    continue

                with self._lock:
                    current = self._await_queue.get(serial)
                if not current:
                    continue

                refreshed = self._classification_strategy.refresh_await_device(serial, current)

                with self._lock:
                    current = self._await_queue.get(serial)
                    if current is None:
                        continue

                    if isinstance(refreshed, UnknownAdbDevice):
                        ready_device = self._make_unknown_device(current)
                    else:
                        ready_device = refreshed
                    self._await_queue.pop(serial, None)
                    self._ready_queue[serial] = ready_device

                self._notify_callbacks('device_update', self.get_devices())
                if ready_device.getStatus().strip().lower() == "unauthorized" and ready_device.getUuid():
                    if not getattr(ready_device, '_submitted', False):
                        ready_device._submitted = True
                        self._notify_callbacks('unauthorized_ready', copy.deepcopy(ready_device.to_device_info()))

            except Exception as e:
                logging.error(f"DeviceParser 解析异常: {e}")
                self._notify_callbacks('error', str(e))
                time.sleep(0.2)
