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
from .cube_manager import CubeManager


class DeviceParser:
    def __init__(self, adb_manager: ADBManager):
        self.adb_manager = adb_manager

        self._await_queue: Dict[str, DeviceInfo] = {}
        self._ready_queue: Dict[str, DeviceInfo] = {}
        self._base_devices: Dict[str, DeviceInfo] = {}
        self._classify_queue: List[str] = []
        self._order: List[str] = []

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
            'error': [],
        }

    def _on_cube_update(self, cubes):
        self._notify_callbacks('authenticator_update', cubes)
        self._notify_callbacks('authenticator_serials_update', list(cubes.keys()))

    def start(self):
        if self._running:
            return
        self.cube_manager.start()
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logging.info("DeviceParser 已启动")

    def stop(self):
        self._running = False
        self._wake_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.cube_manager.stop()
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

    def _make_await_device(self, device: DeviceInfo) -> DeviceInfo:
        d = copy.deepcopy(device)
        d.uuid = ""
        d.status = "Checking..."
        return d

    def _make_ready_device(self, device: DeviceInfo, uuid: str, state: str) -> DeviceInfo:
        d = copy.deepcopy(device)
        d.uuid = uuid.strip() if uuid else ""
        d.status = state if state else "Unknown"
        return d

    def _make_unknown_device(self, device: DeviceInfo) -> DeviceInfo:
        d = copy.deepcopy(device)
        d.device_type = "unknown"
        d.uuid = ""
        d.status = "Unknown Device"
        return d

    def add_device(self, device: DeviceInfo):
        """向分类队列添加设备（device_monitor调用）"""
        serial = str(device.serial)
        with self._lock:
            self._base_devices[serial] = copy.deepcopy(device)
            if serial not in self._order:
                self._order.append(serial)
            if serial not in self._classify_queue and not self.cube_manager.has_cube(serial) and serial not in self._await_queue and serial not in self._ready_queue:
                self._classify_queue.append(serial)

        self._wake_event.set()

    def sync_connected_devices(self, devices: List[DeviceInfo]):
        """同步当前连接设备：增删由device_monitor调用"""
        incoming = {str(d.serial): copy.deepcopy(d) for d in devices}
        with self._lock:
            current = set(self._base_devices.keys())
            new = set(incoming.keys())

            removed = current - new
            added = new - current

            for serial in removed:
                self._base_devices.pop(serial, None)
                self._await_queue.pop(serial, None)
                self._ready_queue.pop(serial, None)
                self._classify_queue = [s for s in self._classify_queue if s != serial]
                self._order = [s for s in self._order if s != serial]
                self.cube_manager.remove_cube(serial)

            for serial in added:
                self._base_devices[serial] = incoming[serial]
                if serial not in self._order:
                    self._order.append(serial)
                if serial not in self._classify_queue:
                    self._classify_queue.append(serial)

            # 更新已存在设备基础字段
            for serial in (new & current):
                self._base_devices[serial] = incoming[serial]
                if serial in self._await_queue:
                    self._await_queue[serial].usb_port = incoming[serial].usb_port
                if serial in self._ready_queue:
                    self._ready_queue[serial].usb_port = incoming[serial].usb_port
                    # 未知设备持续触发重分类，避免authenticator误显示在target列表
                    if self._ready_queue[serial].device_type == "unknown" and serial not in self._classify_queue:
                        self._classify_queue.append(serial)

            # 关键逻辑：所有未归类为authenticator的在线设备都持续进入分类队列
            # 避免authenticator因为瞬时失败长期停留在target/unknown列表
            for serial in new:
                if not self.cube_manager.has_cube(serial) and serial not in self._classify_queue:
                    self._classify_queue.append(serial)

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

        # 若不在target队列，则交由CubeManager处理
        if not in_target:
            self.cube_manager.remove_cube(serial)

        self._notify_callbacks('device_update', self.get_devices())

    def refresh_device(self, serial: str):
        """刷新单个设备：ready -> await"""
        serial = str(serial)
        forwarded_to_cube = False
        with self._lock:
            if serial in self._ready_queue:
                dev = self._ready_queue.pop(serial)
                self._await_queue[serial] = self._make_await_device(dev)
            elif serial not in self._await_queue:
                forwarded_to_cube = True

        # 如果不在ready/await队列中，转发给CubeManager
        if forwarded_to_cube:
            self.cube_manager.refresh_cube(serial)

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
        """刷新全部authenticator：触发重新识别与状态校验"""
        with self._lock:
            # ready中的target/unknown也加入重分类，防止authenticator被误留在target列表
            for serial, dev in list(self._ready_queue.items()):
                if dev.device_type in ("target_device", "unknown") and serial not in self._classify_queue:
                    self._classify_queue.append(serial)

            # await中的设备同样加入重分类（去重后不会重复入队）
            for serial in list(self._await_queue.keys()):
                if serial not in self._classify_queue:
                    self._classify_queue.append(serial)

        # authenticator刷新由CubeManager负责
        self.cube_manager.refresh_all_cube()
        self._wake_event.set()

    def get_devices(self) -> List[DeviceInfo]:
        """获取当前显示设备（await+ready，保持顺序）"""
        with self._lock:
            out = []
            for serial in self._order:
                if serial in self._ready_queue:
                    dev = self._ready_queue[serial]
                    if dev.device_type in ("target_device", "unknown"):
                        out.append(copy.deepcopy(dev))
                elif serial in self._await_queue:
                    dev = self._await_queue[serial]
                    if dev.device_type in ("target_device", "unknown"):
                        out.append(copy.deepcopy(dev))
            return out

    def get_ready_devices(self) -> List[DeviceInfo]:
        with self._lock:
            return [copy.deepcopy(self._ready_queue[s]) for s in self._order if s in self._ready_queue]

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
                    uuid_result = self.adb_manager.get_device_uuid(classify_serial)
                    state_result = self.adb_manager.get_device_state(classify_serial)
                    uuid = uuid_result.result_data.strip() if uuid_result.success and uuid_result.result_data else ""
                    state = state_result.result_data.strip() if state_result.success and state_result.result_data else "Unknown"
                    transfer_to_cube = False
                    snapshot = None
                    known_cube = self.cube_manager.has_cube(classify_serial)

                    if not uuid_result.success and not state_result.success and not known_cube:
                        snapshot = self.adb_manager.get_authenticator_snapshot(classify_serial)

                    with self._lock:
                        base = self._base_devices.get(classify_serial)
                        if not base:
                            continue
                        if uuid_result.success or state_result.success:
                            # 优先按target设备路径处理，减少额外snapshot命令带来的接入时延
                            base.device_type = "target_device"
                            self._await_queue.pop(classify_serial, None)
                            self._ready_queue[classify_serial] = self._make_ready_device(base, uuid=uuid, state=state)
                        else:
                            if snapshot and snapshot.success:
                                # 识别为激活盒子
                                base.device_type = "authenticator"
                                self._await_queue.pop(classify_serial, None)
                                self._ready_queue.pop(classify_serial, None)
                                # 移交给CubeManager管理
                                transfer_to_cube = True
                            # snapshot失败时：已识别过authenticator的设备不降级，避免显示到target列表
                            elif known_cube:
                                base.device_type = "authenticator"
                                self._await_queue.pop(classify_serial, None)
                                self._ready_queue.pop(classify_serial, None)
                                transfer_to_cube = False
                            else:
                                # 新设备按target处理，进入await
                                base.device_type = "target_device"
                                if classify_serial not in self._ready_queue and classify_serial not in self._await_queue:
                                    self._await_queue[classify_serial] = self._make_await_device(base)
                                transfer_to_cube = False

                    if snapshot and snapshot.success and transfer_to_cube:
                        self.cube_manager.add_cube(classify_serial)

                    self._notify_callbacks('device_update', self.get_devices())
                    continue

                serial = self._next_await_serial()
                if not serial:
                    self._wake_event.wait(timeout=0.5)
                    self._wake_event.clear()
                    continue

                with self._lock:
                    base = self._await_queue.get(serial)
                if not base:
                    continue

                uuid_result = self.adb_manager.get_device_uuid(serial)
                state_result = self.adb_manager.get_device_state(serial)

                uuid = uuid_result.result_data.strip() if uuid_result.success and uuid_result.result_data else ""
                state = state_result.result_data.strip() if state_result.success and state_result.result_data else "Unknown"

                with self._lock:
                    current = self._await_queue.get(serial)
                    if current is None:
                        # 设备已被移除
                        continue

                    # target_device解析失败（uuid/state都失败）时显示未知设备
                    if not uuid_result.success and not state_result.success:
                        ready_device = self._make_unknown_device(current)
                    else:
                        ready_device = self._make_ready_device(current, uuid=uuid, state=state)
                    self._await_queue.pop(serial, None)
                    self._ready_queue[serial] = ready_device

                self._notify_callbacks('device_update', self.get_devices())

            except Exception as e:
                logging.error(f"DeviceParser 解析异常: {e}")
                self._notify_callbacks('error', str(e))
                time.sleep(0.2)
