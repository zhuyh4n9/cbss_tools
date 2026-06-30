import copy
import queue
import threading
import time
import unittest

from src.adb_manager import CommandResult, DeviceInfo, AuthenticatorInfo
from src.device_parser import DeviceParser
from src.cube_manager import CubeManager
from src.target_device import AC8267Device, TargetDeviceAbstract


class _FakeAdbManager:
    def __init__(self):
        self._uuid_counter = 0
        self._state_counter = 0
        self._snapshot_counter = 0
        self._lock = threading.Lock()

    def __deepcopy__(self, memo):
        return self

    def get_device_uuid(self, serial: str):
        with self._lock:
            self._uuid_counter += 1
        return CommandResult(success=True, status_code=0, result_data="ab" * 32, raw_output="")

    def get_device_state(self, serial: str):
        with self._lock:
            self._state_counter += 1
        return CommandResult(success=True, status_code=0, result_data="Unauthorized", raw_output="")

    def get_authenticator_snapshot(self, serial: str):
        with self._lock:
            self._snapshot_counter += 1
        return CommandResult(success=False, status_code=1, error_message="N/A")


class _SlowAdbManager(_FakeAdbManager):
    def __init__(self, delay: float = 0.1):
        super().__init__()
        self.delay = delay

    def get_device_uuid(self, serial: str):
        time.sleep(self.delay)
        return super().get_device_uuid(serial)

    def get_device_state(self, serial: str):
        time.sleep(self.delay)
        return super().get_device_state(serial)


class TestConcurrentDeviceAddRemove(unittest.TestCase):
    def setUp(self):
        self.adb = _FakeAdbManager()
        self.parser = DeviceParser(self.adb)
        self.updates = []
        self.parser.add_callback('device_update', lambda devices: self.updates.append(list(devices)))
        self.parser.start()

    def tearDown(self):
        self.parser.stop(join_timeout=2.0)

    def _wait_updates(self, min_count: int, timeout: float = 3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if len(self.updates) >= min_count:
                return True
            time.sleep(0.02)
        return False

    def test_concurrent_add_multiple_devices(self):
        count = 10
        threads = []
        for i in range(count):
            serial = f"DEV-CONC-{i:03d}"
            t = threading.Thread(
                target=lambda s=serial: self.parser.add_device(
                    DeviceInfo(serial=s, status="Unknown", detection_method="Adb", usb_port=f"USB{i}")
                )
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        deadline = time.time() + 8.0
        while time.time() < deadline:
            ready = self.parser.get_ready_devices()
            ready_serials = {d.serial for d in ready}
            if all(f"DEV-CONC-{i:03d}" in ready_serials for i in range(count)):
                break
            time.sleep(0.1)

        ready = self.parser.get_ready_devices()
        ready_serials = {d.serial for d in ready}
        for i in range(count):
            expected = f"DEV-CONC-{i:03d}"
            self.assertIn(expected, ready_serials, f"设备 {expected} 未出现在 ready 队列中")

    def test_concurrent_add_and_remove(self):
        keep_serials = {f"DEV-KEEP-{i:03d}" for i in range(5)}
        remove_serials = {f"DEV-DEL-{i:03d}" for i in range(5)}

        add_threads = []
        for serial in (keep_serials | remove_serials):
            t = threading.Thread(
                target=lambda s=serial: self.parser.add_device(
                    DeviceInfo(serial=s, status="Unknown", detection_method="Adb", usb_port="USB1")
                )
            )
            add_threads.append(t)

        for t in add_threads:
            t.start()
        for t in add_threads:
            t.join()

        self.assertTrue(self._wait_updates(min_count=1, timeout=5.0))

        remove_threads = []
        for serial in remove_serials:
            t = threading.Thread(target=lambda s=serial: self.parser.remove_device(s))
            remove_threads.append(t)

        for t in remove_threads:
            t.start()
        for t in remove_threads:
            t.join()

        time.sleep(0.5)

        ready = self.parser.get_ready_devices()
        ready_serials = {d.serial for d in ready}
        for serial in keep_serials:
            self.assertIn(serial, ready_serials, f"保留设备 {serial} 不应被移除")
        for serial in remove_serials:
            self.assertNotIn(serial, ready_serials, f"移除设备 {serial} 不应出现在 ready 队列")


class TestConcurrentMarkDirtyLock(unittest.TestCase):
    def test_concurrent_mark_dirty_and_lock(self):
        adb = _FakeAdbManager()
        device = AC8267Device(
            serial_number="DEV-LOCK-001",
            adb_manager=adb,
            uuid="uuid-001",
            status="Unauthorized",
        )

        kick_calls = []
        kick_count = threading.Lock()

        def fake_kick():
            with kick_count:
                kick_calls.append(1)

        errors = []
        barrier = threading.Barrier(4, timeout=3.0)

        def worker():
            try:
                barrier.wait()
                for _ in range(50):
                    device.markDirty(fake_kick)
                    device.lock()
                    device.unlock(fake_kick)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发 markDirty/lock/unlock 出现异常: {errors}")

    def test_concurrent_lock_unlock_state_consistency(self):
        adb = _FakeAdbManager()
        device = AC8267Device(
            serial_number="DEV-CONSIST-001",
            adb_manager=adb,
            uuid="uuid-001",
            status="Unauthorized",
        )

        results = []
        results_lock = threading.Lock()

        def worker():
            for _ in range(30):
                device.lock()
                locked = device.isLocked()
                device.unlock(lambda: None)
                with results_lock:
                    results.append(locked)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertFalse(device.isLocked(), "最终状态应为未锁定")
        self.assertTrue(all(results), "lock() 返回后 isLocked() 应始终为 True")


class TestConcurrentCubeManager(unittest.TestCase):
    def setUp(self):
        self.adb = _FakeAdbManager()
        self.cm = CubeManager(self.adb, refresh_interval=10)
        self.updates = []
        self.cm.add_callback('authenticator_update', lambda data: self.updates.append(dict(data)))
        self.cm.start()

    def tearDown(self):
        self.cm.stop(join_timeout=2.0)

    def test_concurrent_add_multiple_cubes(self):
        count = 8
        threads = []
        for i in range(count):
            serial = f"CUBE-CONC-{i:03d}"
            t = threading.Thread(target=lambda s=serial: self.cm.add_cube(s))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(0.5)

        with self.cm._lock:
            pending = set(self.cm._pending_cubes)
        for i in range(count):
            expected = f"CUBE-CONC-{i:03d}"
            self.assertIn(expected, pending, f"Cube {expected} 未出现在 pending 集合")

    def test_concurrent_add_and_remove_cubes(self):
        keep = {f"CUBE-KEEP-{i:03d}" for i in range(4)}
        remove = {f"CUBE-DEL-{i:03d}" for i in range(4)}

        add_threads = []
        for serial in (keep | remove):
            t = threading.Thread(target=lambda s=serial: self.cm.add_cube(s))
            add_threads.append(t)

        for t in add_threads:
            t.start()
        for t in add_threads:
            t.join()

        time.sleep(0.3)

        remove_threads = []
        for serial in remove:
            t = threading.Thread(target=lambda s=serial: self.cm.remove_cube(s))
            remove_threads.append(t)

        for t in remove_threads:
            t.start()
        for t in remove_threads:
            t.join()

        time.sleep(0.3)

        with self.cm._lock:
            cubes = set(self.cm._cubes.keys())
            pending = set(self.cm._pending_cubes)
            refresh = set(self.cm._refresh_queue)

        for serial in keep:
            in_system = serial in cubes or serial in pending or serial in refresh
            self.assertTrue(in_system, f"保留 Cube {serial} 不应被完全移除")

        for serial in remove:
            self.assertNotIn(serial, cubes, f"移除 Cube {serial} 不应在 cubes 中")

    def test_concurrent_refresh_all_and_add(self):
        for i in range(3):
            self.cm.add_cube(f"CUBE-BASE-{i:03d}")
        time.sleep(0.5)

        errors = []

        def refresh_worker():
            try:
                for _ in range(10):
                    self.cm.refresh_all_cube()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(str(e))

        def add_worker():
            try:
                for i in range(10):
                    self.cm.add_cube(f"CUBE-ADD-{i:03d}")
                    time.sleep(0.01)
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=refresh_worker),
            threading.Thread(target=add_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发 refresh/add 出现异常: {errors}")


class TestConcurrentAuthLock(unittest.TestCase):
    def test_authentication_lock_prevents_concurrent_auth(self):
        lock = threading.Lock()
        active_count = 0
        max_concurrent = 0
        count_lock = threading.Lock()
        results = []

        def simulated_auth(worker_id: int):
            nonlocal active_count, max_concurrent
            with lock:
                with count_lock:
                    active_count += 1
                    max_concurrent = max(max_concurrent, active_count)

                time.sleep(0.05)

                with count_lock:
                    active_count -= 1

                results.append(worker_id)

        threads = [threading.Thread(target=simulated_auth, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(max_concurrent, 1, "认证锁应保证同时只有一个认证在执行")
        self.assertEqual(len(results), 10, "所有认证请求都应完成")


class TestConcurrentAutoActivationQueue(unittest.TestCase):
    def test_queue_thread_safety(self):
        q = queue.Queue()
        queued = set()
        queued_lock = threading.Lock()
        errors = []

        def producer(start: int, count: int):
            try:
                for i in range(start, start + count):
                    serial = f"DEV-QUEUE-{i:04d}"
                    with queued_lock:
                        if serial not in queued:
                            queued.add(serial)
                            q.put(serial)
            except Exception as e:
                errors.append(str(e))

        def consumer():
            try:
                for _ in range(50):
                    try:
                        q.get(timeout=0.1)
                    except queue.Empty:
                        break
            except Exception as e:
                errors.append(str(e))

        producers = [
            threading.Thread(target=producer, args=(0, 50)),
            threading.Thread(target=producer, args=(25, 50)),
            threading.Thread(target=producer, args=(50, 50)),
        ]
        consumer_thread = threading.Thread(target=consumer)

        for t in producers:
            t.start()
        consumer_thread.start()

        for t in producers:
            t.join()
        consumer_thread.join()

        self.assertEqual(len(errors), 0, f"队列并发操作出现异常: {errors}")


class TestConcurrentDeviceParserKick(unittest.TestCase):
    def setUp(self):
        self.adb = _SlowAdbManager(delay=0.02)
        self.parser = DeviceParser(self.adb)
        self.updates = []
        self.parser.add_callback('device_update', lambda devices: self.updates.append(list(devices)))
        self.parser.start()

    def tearDown(self):
        self.parser.stop(join_timeout=2.0)

    def _wait_ready(self, serial: str, timeout: float = 3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready = self.parser.get_ready_devices()
            if any(d.serial == serial for d in ready):
                return True
            time.sleep(0.02)
        return False

    def test_concurrent_kick_trigger_multiple_devices(self):
        count = 6
        serials = [f"DEV-KICK-{i:03d}" for i in range(count)]

        for serial in serials:
            self.parser.add_device(
                DeviceInfo(serial=serial, status="Unknown", detection_method="Adb", usb_port="USB1")
            )

        for serial in serials:
            self.assertTrue(self._wait_ready(serial, timeout=5.0), f"设备 {serial} 未就绪")

        kick_threads = []
        for serial in serials:
            t = threading.Thread(target=lambda s=serial: self.parser.kick_trigger(s))
            kick_threads.append(t)

        for t in kick_threads:
            t.start()
        for t in kick_threads:
            t.join()

        time.sleep(1.0)

        ready = self.parser.get_ready_devices()
        ready_serials = {d.serial for d in ready}
        for serial in serials:
            self.assertIn(serial, ready_serials, f"kick 后设备 {serial} 应回到 ready 队列")


class TestConcurrentDeviceMonitorDetectors(unittest.TestCase):
    def test_concurrent_detector_polling(self):
        class _FakeDetector:
            def __init__(self, name: str):
                self.name = name
                self._lock = threading.Lock()
                self.poll_count = 0

            def get_name(self):
                return self.name

            def poll_changes(self):
                with self._lock:
                    self.poll_count += 1
                from src.device_source import DeviceChange
                return DeviceChange(added=[], removed=[])

        detectors = [_FakeDetector(f"Detector-{i}") for i in range(4)]
        errors = []

        def poll_worker():
            try:
                for _ in range(20):
                    for d in detectors:
                        d.poll_changes()
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=poll_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发探测器轮询出现异常: {errors}")
        for d in detectors:
            self.assertEqual(d.poll_count, 80, f"{d.name} 轮询次数应为 80")


class TestConcurrentDeepCopySafety(unittest.TestCase):
    def test_concurrent_deepcopy_of_device_list(self):
        devices = [
            DeviceInfo(serial=f"DEV-DC-{i:03d}", status="Unauthorized", uuid=f"uuid-{i:03d}")
            for i in range(20)
        ]
        devices_lock = threading.Lock()
        errors = []

        def copy_worker():
            try:
                for _ in range(50):
                    with devices_lock:
                        snapshot = copy.deepcopy(devices)
                    self.assertGreaterEqual(len(snapshot), 1)
            except Exception as e:
                errors.append(str(e))

        def mutate_worker():
            try:
                for _ in range(50):
                    with devices_lock:
                        devices.append(
                            DeviceInfo(serial=f"DEV-DC-MUT-{len(devices):03d}", status="Unknown")
                        )
                        if len(devices) > 30:
                            devices.pop(0)
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=copy_worker),
            threading.Thread(target=copy_worker),
            threading.Thread(target=mutate_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发 deepcopy 出现异常: {errors}")


if __name__ == "__main__":
    unittest.main()