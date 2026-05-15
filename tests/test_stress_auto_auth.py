import os
import tempfile
import threading
import time
import unittest

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from src.adb_manager import ADBManager, CommandResult, DeviceInfo
from src.auth_manager import AuthenticationManager
from src.config_manager import ConfigManager
from src.device_monitor import DeviceMonitor


def _generate_test_p256_key() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
        f.write(pem.decode("utf-8"))
        return f.name


class _TestAdbManager(ADBManager):
    def __init__(self, config_manager):
        super().__init__(config_manager)

    def get_connected_devices(self):
        return []

    def execute_adb_command(self, command, serial=None):
        return CommandResult(False, 1, error_message="ADB not available in test")

    def get_device_uuid(self, serial):
        return CommandResult(False, 1, error_message="ADB not available in test")

    def get_device_state(self, serial):
        return CommandResult(False, 1, error_message="ADB not available in test")

    def get_authenticator_snapshot(self, serial):
        return CommandResult(False, 1, error_message="ADB not available in test")


class _TestableAuthManager(AuthenticationManager):
    def __init__(self, adb_manager, device_monitor):
        super().__init__(adb_manager, device_monitor)
        self._processed_serials = []
        self._processed_lock = threading.Lock()

    def _run_authentication(self, device_serial, authenticator_serial, progress_callback=None):
        with self._processed_lock:
            self._processed_serials.append(device_serial)
        return {"success": True}


class StressTestBase(unittest.TestCase):
    KEY_PATH = None
    PERSIST_DIR = None

    @classmethod
    def setUpClass(cls):
        cls.KEY_PATH = _generate_test_p256_key()
        cls.PERSIST_DIR = tempfile.mkdtemp(prefix="stress_test_")

    @classmethod
    def tearDownClass(cls):
        if cls.KEY_PATH and os.path.exists(cls.KEY_PATH):
            os.unlink(cls.KEY_PATH)
        if cls.PERSIST_DIR and os.path.exists(cls.PERSIST_DIR):
            import shutil
            shutil.rmtree(cls.PERSIST_DIR, ignore_errors=True)

    def _create_monitor(self):
        config = ConfigManager()
        adb = _TestAdbManager(config)
        monitor = DeviceMonitor(adb_manager=adb, config_manager=config)
        return monitor, adb, config

    def _create_cube(self, monitor, counter=100):
        persist_path = os.path.join(self.PERSIST_DIR, f"cube_{int(time.time() * 1000)}.json")
        serial = monitor.create_simulated_cube(
            expired_date="2099-12-31",
            counter=counter,
            private_key_path=self.KEY_PATH,
            cube_id="",
            oem_id="",
            persist_path=persist_path,
        )
        return serial

    def _create_device(self, monitor, status="Unauthorized", serial_number="",
                       simulate_activate_failure=False):
        return monitor.add_simulated_device(
            status=status,
            serial_number=serial_number,
            simulate_activate_failure=simulate_activate_failure,
        )

    def _wait_for_queue_empty(self, manager, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with manager._queue_lock:
                remaining = len(manager._queued_serials) + len(manager._in_progress_serials)
            if remaining == 0:
                time.sleep(0.3)
                with manager._queue_lock:
                    remaining2 = len(manager._queued_serials) + len(manager._in_progress_serials)
                if remaining2 == 0:
                    return True
            time.sleep(0.1)
        return False

    def _wait_for_processed_count(self, manager, min_count, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with manager._processed_lock:
                processed = len(manager._processed_serials)
            if processed >= min_count:
                return True
            time.sleep(0.1)
        return False

    def _wait_for_completed_count(self, manager, min_count, timeout=30.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with manager._queue_lock:
                completed = len(manager._auto_activation_completed_serials)
            if completed >= min_count:
                return True
            time.sleep(0.2)
        return False

    def _is_device_authorized(self, serial):
        for device in self.monitor.target_devices:
            if str(device.serial) == serial:
                return (device.status or "").strip().lower() == "authorized"
        return False


class TestStressAutoAuthHighVolume(StressTestBase):
    def setUp(self):
        self.monitor, self.adb, self.config = self._create_monitor()
        self.cube_serial = self._create_cube(self.monitor, counter=200)
        self.monitor.start_monitoring()
        self.manager = _TestableAuthManager(adb_manager=self.adb, device_monitor=self.monitor)

    def tearDown(self):
        try:
            self.manager.set_auto_activation_enabled(False)
            self.manager.stop(join_timeout=5.0)
        finally:
            self.monitor.stop_monitoring(join_timeout=5.0)

    def test_high_volume_concurrent_enqueue(self):
        device_count = 50
        self.manager.set_auto_activation_enabled(True)

        for i in range(device_count):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-HV-{i:04d}")

        deadline = time.time() + 20.0
        while time.time() < deadline:
            with self.manager._queue_lock:
                remaining = len(self.manager._queued_serials) + len(self.manager._in_progress_serials)
            with self.manager._processed_lock:
                processed = len(self.manager._processed_serials)
            if remaining == 0 and processed >= device_count:
                break
            time.sleep(0.2)

        with self.manager._queue_lock:
            remaining = len(self.manager._queued_serials) + len(self.manager._in_progress_serials)
        with self.manager._processed_lock:
            processed = len(self.manager._processed_serials)

        self.assertEqual(remaining, 0, f"队列仍有 {remaining} 个设备未处理")
        self.assertGreaterEqual(processed, device_count,
                                f"应处理至少 {device_count} 个设备，实际处理 {processed}")

        with self.manager._queue_lock:
            completed = set(self.manager._auto_activation_completed_serials)
        for i in range(device_count):
            expected = f"DEV-HV-{i:04d}"
            self.assertIn(expected, completed, f"设备 {expected} 未标记为自动授权完成")

    def test_duplicate_serial_prevention(self):
        self.manager.set_auto_activation_enabled(True)
        serial = "DEV-DUP-0001"
        self._create_device(self.monitor, status="Unauthorized", serial_number=serial)

        time.sleep(1.0)

        for _ in range(20):
            self.manager._on_unauthorized_ready(
                DeviceInfo(serial=serial, status="Unauthorized", uuid="ab" * 32)
            )

        time.sleep(0.5)

        with self.manager._queue_lock:
            queued = self.manager._queued_serials.copy()
            in_progress = self.manager._in_progress_serials.copy()

        self.assertLessEqual(len(queued) + len(in_progress), 1,
                             f"重复 serial 应只入队一次，实际 queued={queued}, in_progress={in_progress}")

    def test_queue_consistency_under_load(self):
        device_count = 30
        self.manager.set_auto_activation_enabled(True)

        for i in range(device_count):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-QC-{i:04d}")

        self.assertTrue(self._wait_for_queue_empty(self.manager, timeout=15.0))

        with self.manager._queue_lock:
            queued = set(self.manager._queued_serials)
            in_progress = set(self.manager._in_progress_serials)
            completed = set(self.manager._auto_activation_completed_serials)

        overlap_qp = queued & in_progress
        self.assertEqual(len(overlap_qp), 0,
                         f"queued 和 in_progress 不应有交集: {overlap_qp}")

        overlap_qc = queued & completed
        self.assertEqual(len(overlap_qc), 0,
                         f"queued 和 completed 不应有交集: {overlap_qc}")

        overlap_pc = in_progress & completed
        self.assertEqual(len(overlap_pc), 0,
                         f"in_progress 和 completed 不应有交集: {overlap_pc}")


class TestStressAutoAuthToggle(StressTestBase):
    def setUp(self):
        self.monitor, self.adb, self.config = self._create_monitor()
        self.cube_serial = self._create_cube(self.monitor, counter=100)
        self.monitor.start_monitoring()
        self.manager = _TestableAuthManager(adb_manager=self.adb, device_monitor=self.monitor)

    def tearDown(self):
        try:
            self.manager.set_auto_activation_enabled(False)
            self.manager.stop(join_timeout=5.0)
        finally:
            self.monitor.stop_monitoring(join_timeout=5.0)

    def test_rapid_enable_disable_toggle(self):
        toggle_count = 20
        errors = []

        def toggle_worker():
            try:
                for _ in range(toggle_count):
                    self.manager.set_auto_activation_enabled(True)
                    time.sleep(0.01)
                    self.manager.set_auto_activation_enabled(False)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(str(e))

        t = threading.Thread(target=toggle_worker)
        t.start()
        t.join()

        self.manager.set_auto_activation_enabled(False)
        self.manager.stop(join_timeout=5.0)

        self.assertEqual(len(errors), 0, f"快速切换开关出现异常: {errors}")
        self.assertFalse(self.manager._worker_running, "最终 worker 应已停止")

    def test_enqueue_during_toggle(self):
        device_count = 10
        for i in range(device_count):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-TOG-{i:04d}")

        time.sleep(1.0)

        errors = []

        def toggle_worker():
            try:
                for _ in range(15):
                    self.manager.set_auto_activation_enabled(True)
                    time.sleep(0.02)
                    self.manager.set_auto_activation_enabled(False)
                    time.sleep(0.02)
            except Exception as e:
                errors.append(f"toggle: {e}")

        def enqueue_worker():
            try:
                for i in range(device_count):
                    serial = f"DEV-TOG-{i:04d}"
                    self.manager._on_unauthorized_ready(
                        DeviceInfo(serial=serial, status="Unauthorized", uuid="ab" * 32)
                    )
                    time.sleep(0.01)
            except Exception as e:
                errors.append(f"enqueue: {e}")

        t_toggle = threading.Thread(target=toggle_worker)
        t_enqueue = threading.Thread(target=enqueue_worker)
        t_toggle.start()
        t_enqueue.start()
        t_toggle.join()
        t_enqueue.join()

        self.manager.set_auto_activation_enabled(False)
        self.manager.stop(join_timeout=5.0)

        self.assertEqual(len(errors), 0, f"并发切换/入队出现异常: {errors}")

    def test_worker_restart_under_load(self):
        self.manager.set_auto_activation_enabled(True)

        for i in range(5):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-RST-{i:04d}")

        time.sleep(2.0)

        self.manager.set_auto_activation_enabled(False)
        self.manager.stop(join_timeout=5.0)

        self.assertFalse(self.manager._worker_running)

        for i in range(5, 10):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-RST-{i:04d}")

        time.sleep(2.0)

        self.manager.set_auto_activation_enabled(True)

        self.assertTrue(self._wait_for_queue_empty(self.manager, timeout=15.0))

        with self.manager._processed_lock:
            processed = self.manager._processed_serials

        for i in range(5, 10):
            expected = f"DEV-RST-{i:04d}"
            self.assertIn(expected, processed,
                          f"重启 worker 后设备 {expected} 应被处理")


class TestStressAutoAuthNoAuthenticator(StressTestBase):
    def setUp(self):
        self.monitor, self.adb, self.config = self._create_monitor()
        self.monitor.start_monitoring()
        self.manager = _TestableAuthManager(adb_manager=self.adb, device_monitor=self.monitor)

    def tearDown(self):
        try:
            self.manager.set_auto_activation_enabled(False)
            self.manager.stop(join_timeout=5.0)
        finally:
            self.monitor.stop_monitoring(join_timeout=5.0)

    def test_no_authenticator_retry_does_not_crash(self):
        self.manager.set_auto_activation_enabled(True)

        for i in range(10):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-NOA-{i:04d}")

        time.sleep(2.0)

        self.assertTrue(self.manager._worker_running,
                        "无 Cube 时 worker 不应崩溃")

        self._create_cube(self.monitor, counter=50)

        self.assertTrue(self._wait_for_queue_empty(self.manager, timeout=15.0))

        with self.manager._processed_lock:
            processed = len(self.manager._processed_serials)
        self.assertGreaterEqual(processed, 10,
                                f"添加 Cube 后应处理所有设备，实际处理 {processed}")

    def test_authenticator_appears_mid_processing(self):
        self.manager.set_auto_activation_enabled(True)

        for i in range(8):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-MID-{i:04d}")

        time.sleep(1.0)

        self._create_cube(self.monitor, counter=50)

        self.assertTrue(self._wait_for_queue_empty(self.manager, timeout=15.0))

        with self.manager._processed_lock:
            processed = len(self.manager._processed_serials)
        self.assertGreaterEqual(processed, 8,
                                f"中途出现 Cube 后应处理所有设备，实际处理 {processed}")


class TestStressAutoAuthDeviceRemoval(StressTestBase):
    def setUp(self):
        self.monitor, self.adb, self.config = self._create_monitor()
        self.cube_serial = self._create_cube(self.monitor, counter=100)
        self.monitor.start_monitoring()
        self.manager = _TestableAuthManager(adb_manager=self.adb, device_monitor=self.monitor)

    def tearDown(self):
        try:
            self.manager.set_auto_activation_enabled(False)
            self.manager.stop(join_timeout=5.0)
        finally:
            self.monitor.stop_monitoring(join_timeout=5.0)

    def test_device_removed_while_queued(self):
        self.manager.set_auto_activation_enabled(True)

        keep_serials = {f"DEV-KEEP-{i:04d}" for i in range(5)}
        remove_serials = {f"DEV-DEL-{i:04d}" for i in range(5)}

        for serial in (keep_serials | remove_serials):
            self._create_device(self.monitor, status="Unauthorized", serial_number=serial)

        time.sleep(1.0)

        for serial in remove_serials:
            self.monitor.remove_simulated_device(serial)

        self.assertTrue(self._wait_for_queue_empty(self.manager, timeout=15.0))

        with self.manager._processed_lock:
            processed = set(self.manager._processed_serials)

        for serial in keep_serials:
            self.assertIn(serial, processed,
                          f"保留设备 {serial} 应被处理")

    def test_concurrent_remove_and_enqueue(self):
        self.manager.set_auto_activation_enabled(True)

        all_serials = {f"DEV-CRE-{i:04d}" for i in range(20)}
        remove_serials = {f"DEV-CRE-{i:04d}" for i in range(0, 20, 2)}
        keep_serials = all_serials - remove_serials

        for serial in all_serials:
            self._create_device(self.monitor, status="Unauthorized", serial_number=serial)

        time.sleep(1.0)

        errors = []

        def enqueue_worker():
            try:
                for serial in all_serials:
                    self.manager._on_unauthorized_ready(
                        DeviceInfo(serial=serial, status="Unauthorized", uuid="ab" * 32)
                    )
            except Exception as e:
                errors.append(f"enqueue: {e}")

        def remove_worker():
            try:
                time.sleep(0.1)
                for serial in remove_serials:
                    self.monitor.remove_simulated_device(serial)
            except Exception as e:
                errors.append(f"remove: {e}")

        t1 = threading.Thread(target=enqueue_worker)
        t2 = threading.Thread(target=remove_worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"并发入队/移除出现异常: {errors}")

        self.assertTrue(self._wait_for_queue_empty(self.manager, timeout=15.0))

        with self.manager._processed_lock:
            processed = set(self.manager._processed_serials)

        for serial in keep_serials:
            self.assertIn(serial, processed,
                          f"保留设备 {serial} 应被处理")


class TestStressAutoAuthRaceConditions(StressTestBase):
    def setUp(self):
        self.monitor, self.adb, self.config = self._create_monitor()
        self.cube_serial = self._create_cube(self.monitor, counter=200)
        self.monitor.start_monitoring()
        self.manager = _TestableAuthManager(adb_manager=self.adb, device_monitor=self.monitor)

    def tearDown(self):
        try:
            self.manager.set_auto_activation_enabled(False)
            self.manager.stop(join_timeout=5.0)
        finally:
            self.monitor.stop_monitoring(join_timeout=5.0)

    def test_concurrent_on_unauthorized_ready_multi_thread(self):
        self.manager.set_auto_activation_enabled(True)

        device_count = 30
        for i in range(device_count):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-MT-{i:04d}")

        time.sleep(1.0)

        threads = []
        for i in range(device_count):
            serial = f"DEV-MT-{i:04d}"
            t = threading.Thread(
                target=lambda s=serial: self.manager._on_unauthorized_ready(
                    DeviceInfo(serial=s, status="Unauthorized", uuid="ab" * 32)
                )
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        with self.manager._queue_lock:
            queued_count = len(self.manager._queued_serials)
            in_progress_count = len(self.manager._in_progress_serials)

        self.assertLessEqual(queued_count + in_progress_count, device_count,
                             f"入队数量不应超过设备总数 {device_count}")

        self.assertTrue(self._wait_for_queue_empty(self.manager, timeout=20.0))

        with self.manager._processed_lock:
            processed = len(self.manager._processed_serials)
        self.assertGreaterEqual(processed, device_count,
                                f"应处理至少 {device_count} 个设备，实际处理 {processed}")

    def test_queue_lock_contention(self):
        self.manager.set_auto_activation_enabled(True)

        for i in range(20):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-LC-{i:04d}")

        time.sleep(1.0)

        errors = []
        iterations = 200

        def contention_worker():
            try:
                for _ in range(iterations):
                    with self.manager._queue_lock:
                        _ = self.manager._queued_serials.copy()
                        _ = self.manager._in_progress_serials.copy()
                        _ = self.manager._auto_activation_completed_serials.copy()
            except Exception as e:
                errors.append(str(e))

        def enqueue_worker():
            try:
                for i in range(20):
                    serial = f"DEV-LC-{i:04d}"
                    self.manager._on_unauthorized_ready(
                        DeviceInfo(serial=serial, status="Unauthorized", uuid="ab" * 32)
                    )
            except Exception as e:
                errors.append(f"enqueue: {e}")

        threads = [threading.Thread(target=contention_worker) for _ in range(4)]
        threads.append(threading.Thread(target=enqueue_worker))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"_queue_lock 并发争用出现异常: {errors}")

    def test_is_device_queued_thread_safety(self):
        self.manager.set_auto_activation_enabled(True)

        for i in range(10):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-QS-{i:04d}")

        time.sleep(1.0)

        errors = []
        results = []
        results_lock = threading.Lock()

        def query_worker():
            try:
                for _ in range(100):
                    for i in range(10):
                        serial = f"DEV-QS-{i:04d}"
                        queued = self.manager.is_device_queued_for_auto_activation(serial)
                        completed = self.manager.is_device_auto_activation_completed(serial)
                        with results_lock:
                            results.append((serial, queued, completed))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=query_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发查询队列状态出现异常: {errors}")

        for serial, queued, completed in results:
            self.assertFalse(queued and completed,
                             f"设备 {serial} 不应同时处于 queued 和 completed 状态")


class TestStressAutoAuthRealActivation(StressTestBase):
    def setUp(self):
        self.monitor, self.adb, self.config = self._create_monitor()
        self.cube_serial = self._create_cube(self.monitor, counter=200)
        self.monitor.start_monitoring()
        self.manager = AuthenticationManager(adb_manager=self.adb, device_monitor=self.monitor)

    def tearDown(self):
        try:
            self.manager.set_auto_activation_enabled(False)
            self.manager.stop(join_timeout=5.0)
        finally:
            self.monitor.stop_monitoring(join_timeout=5.0)

    def test_real_activation_flow_concurrent(self):
        device_count = 20
        self.manager.set_auto_activation_enabled(True)

        for i in range(device_count):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-REAL-{i:04d}")

        self.assertTrue(self._wait_for_completed_count(self.manager, device_count, timeout=30.0),
                        f"超时未完成 {device_count} 个设备的真实激活")

        with self.manager._queue_lock:
            remaining = len(self.manager._queued_serials) + len(self.manager._in_progress_serials)
            completed = set(self.manager._auto_activation_completed_serials)

        self.assertEqual(remaining, 0, f"队列仍有 {remaining} 个设备未处理")
        self.assertGreaterEqual(len(completed), device_count,
                                f"应完成至少 {device_count} 个设备，实际完成 {len(completed)}")

        for i in range(device_count):
            expected = f"DEV-REAL-{i:04d}"
            self.assertIn(expected, completed,
                          f"设备 {expected} 未完成真实激活")

    def test_real_activation_with_failures(self):
        device_count = 10
        self.manager.set_auto_activation_enabled(True)

        for i in range(device_count):
            fail = (i % 3 == 0)
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-FAIL-{i:04d}",
                                simulate_activate_failure=fail)

        deadline = time.time() + 30.0
        while time.time() < deadline:
            with self.manager._queue_lock:
                remaining = len(self.manager._queued_serials) + len(self.manager._in_progress_serials)
            if remaining == 0:
                break
            time.sleep(0.2)

        with self.manager._queue_lock:
            remaining = len(self.manager._queued_serials) + len(self.manager._in_progress_serials)

        self.assertEqual(remaining, 0, f"队列仍有 {remaining} 个设备未处理")

    def test_real_activation_rapid_toggle(self):
        self.manager.set_auto_activation_enabled(True)

        for i in range(5):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-RT-{i:04d}")

        time.sleep(1.0)

        for _ in range(10):
            self.manager.set_auto_activation_enabled(False)
            time.sleep(0.05)
            self.manager.set_auto_activation_enabled(True)
            time.sleep(0.05)

        time.sleep(1.0)
        if not self.manager._worker_running:
            self.manager.set_auto_activation_enabled(True)

        for i in range(5, 10):
            self._create_device(self.monitor, status="Unauthorized",
                                serial_number=f"DEV-RT-{i:04d}")

        self.assertTrue(self._wait_for_queue_empty(self.manager, timeout=30.0),
                        "超时队列未清空")

        with self.manager._queue_lock:
            completed = set(self.manager._auto_activation_completed_serials)

        for i in range(10):
            expected = f"DEV-RT-{i:04d}"
            is_completed = expected in completed
            is_authorized = self._is_device_authorized(expected)
            self.assertTrue(is_completed or is_authorized,
                          f"设备 {expected} 未完成激活且状态非Authorized")


if __name__ == "__main__":
    unittest.main()