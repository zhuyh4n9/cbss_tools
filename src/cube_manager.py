"""
Cube管理器
负责管理Authenticator设备及其周期刷新
"""

import copy
import logging
import threading
import time
from typing import Callable, Dict

from .adb_manager import ADBManager, AuthenticatorInfo


class CubeManager:
    def __init__(self, adb_manager: ADBManager, refresh_interval: int = 5):
        self.adb_manager = adb_manager
        self.refresh_interval = max(int(refresh_interval or 5), 1)

        self._cubes: Dict[str, AuthenticatorInfo] = {}
        self._pending_cubes = set()
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._refresh_queue = set()

        self._callbacks = {
            'authenticator_update': [],
            'error': [],
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        logging.info("CubeManager 已启动")

    def stop(self):
        self._running = False
        self._wake_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        logging.info("CubeManager 已停止")

    def add_callback(self, event_type: str, callback: Callable):
        if event_type in self._callbacks:
            self._callbacks[event_type].append(callback)

    def _notify_callbacks(self, event_type: str, data=None):
        for callback in self._callbacks.get(event_type, []):
            try:
                callback(data)
            except Exception as e:
                logging.error(f"CubeManager 回调执行失败: {e}")

    def has_cube(self, serial: str) -> bool:
        with self._lock:
            s = str(serial)
            return s in self._cubes or s in self._pending_cubes

    def add_cube(self, serial: str):
        serial = str(serial)
        with self._lock:
            self._pending_cubes.add(serial)
            self._refresh_queue.add(serial)
        self._wake_event.set()

    def remove_cube(self, serial: str):
        serial = str(serial)
        changed = False
        with self._lock:
            self._refresh_queue.discard(serial)
            self._pending_cubes.discard(serial)
            if serial in self._cubes:
                self._cubes.pop(serial, None)
                changed = True
        if changed:
            self._notify_callbacks('authenticator_update', self.get_cubes())

    def refresh_cube(self, serial: str):
        serial = str(serial)
        with self._lock:
            self._pending_cubes.add(serial)
            self._refresh_queue.add(serial)
        self._wake_event.set()

    def refresh_all_cube(self):
        with self._lock:
            for serial in self._cubes.keys():
                self._pending_cubes.add(serial)
                self._refresh_queue.add(serial)
        self._wake_event.set()

    def get_cube_serials(self):
        with self._lock:
            return list(self._cubes.keys())

    def get_cubes(self) -> Dict[str, AuthenticatorInfo]:
        with self._lock:
            return copy.deepcopy(self._cubes)

    def _refresh_one(self, serial: str) -> bool:
        result = self.adb_manager.get_authenticator_snapshot(serial)
        if not result.success:
            return False

        auth_info = self.adb_manager.parse_snapshot_data(result.raw_output)
        auth_info.serial = serial

        changed = False
        with self._lock:
            old = self._cubes.get(serial)
            self._cubes[serial] = auth_info
            self._pending_cubes.discard(serial)
            if old is None:
                changed = True
            else:
                changed = (
                    old.expired_date != auth_info.expired_date or
                    old.counter != auth_info.counter or
                    old.authorized_device_num != auth_info.authorized_device_num or
                    old.device_status != auth_info.device_status or
                    old.time_status != auth_info.time_status
                )
        if changed:
            self._notify_callbacks('authenticator_update', self.get_cubes())
        return True

    def _worker_loop(self):
        last_periodic = 0.0
        while self._running:
            try:
                serial = None
                with self._lock:
                    if self._refresh_queue:
                        serial = self._refresh_queue.pop()

                if serial:
                    ok = self._refresh_one(serial)
                    if not ok:
                        # 刷新失败保留pending并重试，避免刚识别到的authenticator被误降级
                        with self._lock:
                            self._pending_cubes.add(serial)
                            self._refresh_queue.add(serial)
                        logging.debug(f"Cube刷新失败: {serial}")
                        time.sleep(0.2)
                    continue

                now = time.time()
                if now - last_periodic >= self.refresh_interval:
                    with self._lock:
                        periodic_serials = list(self._cubes.keys())
                    for s in periodic_serials:
                        self._refresh_one(s)
                    last_periodic = now

                self._wake_event.wait(timeout=0.5)
                self._wake_event.clear()

            except Exception as e:
                logging.error(f"CubeManager 线程异常: {e}")
                self._notify_callbacks('error', str(e))
                time.sleep(0.2)
