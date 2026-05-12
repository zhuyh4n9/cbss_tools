import threading
import time
import unittest

from src.adb_manager import CommandResult, DeviceInfo
from src.device_parser import DeviceParser
from src.target_device import AC8267Device


class _BlockingAdbManager:
    def __init__(self):
        self._uuid_calls = 0
        self._state_calls = 0
        self._refresh_gate = threading.Event()
        self._block_refresh = False

    def __deepcopy__(self, memo):
        return self

    def block_refresh(self):
        self._block_refresh = True
        self._refresh_gate.clear()

    def release_refresh(self):
        self._refresh_gate.set()

    def get_device_uuid(self, serial: str):
        self._uuid_calls += 1
        if self._block_refresh and self._uuid_calls > 1:
            self._refresh_gate.wait(timeout=2.0)
        return CommandResult(success=True, status_code=0, result_data="ab" * 32, raw_output="")

    def get_device_state(self, serial: str):
        self._state_calls += 1
        if self._block_refresh and self._state_calls > 1:
            self._refresh_gate.wait(timeout=2.0)
        return CommandResult(success=True, status_code=0, result_data="Unauthorized", raw_output="")

    def get_authenticator_snapshot(self, serial: str):
        return CommandResult(success=False, status_code=1, error_message="N/A")


class TestDeviceParserKickTrigger(unittest.TestCase):
    _FINAL_UPDATE_WINDOW = 3
    _EXPECTED_REFRESHED_STATUS = "Unauthorized"

    def setUp(self):
        self.adb = _BlockingAdbManager()
        self.parser = DeviceParser(self.adb)
        self.updates = []
        self.parser.add_callback('device_update', self._capture_update)
        self.parser.start()

    def tearDown(self):
        self.adb.release_refresh()
        self.parser.stop(join_timeout=1.0)

    def _capture_update(self, devices):
        snapshot = {device.serial: device.status for device in devices}
        self.updates.append(snapshot)

    def _wait_until(self, predicate, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def test_kick_trigger_marks_refreshing_before_async_refresh(self):
        serial = "DEV-001"
        self.parser.add_device(DeviceInfo(serial=serial, status="Unknown", detection_method="Adb", usb_port="USB1"))
        self.assertTrue(
            self._wait_until(
                lambda: any(update.get(serial) == "Unauthorized" for update in self.updates)
            )
        )

        with self.parser._lock:
            target = self.parser._ready_queue[serial]

        self.adb.block_refresh()
        start = time.time()
        target.markDirty(lambda: self.parser.kick_trigger(serial))
        elapsed = time.time() - start

        self.assertLess(elapsed, 0.2, "kick_trigger should return immediately without blocking the caller")
        self.assertTrue(
            self._wait_until(
                lambda: any(update.get(serial) == "Checking..." for update in self.updates)
            ),
            "device_update should expose a refreshing state before the async refresh completes",
        )

        self.adb.release_refresh()
        self.assertTrue(
            self._wait_until(
                lambda: any(
                    update.get(serial) == "Unauthorized"
                    for update in self.updates[-self._FINAL_UPDATE_WINDOW:]
                )
            )
        )

    def test_kick_trigger_queues_dirty_await_device_for_worker_refresh(self):
        serial = "DEV-AWAIT-001"
        parser = DeviceParser(self.adb)
        # _kick only restores refreshed devices that still exist in _base_devices.
        parser._base_devices[serial] = AC8267Device(
            serial_number=serial,
            adb_manager=self.adb,
            uuid="old-uuid",
            status="Checking...",
        )
        parser._order.append(serial)
        await_device = AC8267Device(
            serial_number=serial,
            adb_manager=self.adb,
            uuid="old-uuid",
            status="Checking...",
        )
        await_device.markDirty()
        parser._await_queue[serial] = await_device

        parser.kick_trigger(serial)

        self.assertEqual(parser._kick_queue, [serial])
        kick_serial = parser._next_kick_serial()
        self.assertEqual(kick_serial, serial)
        parser._kick(kick_serial)

        self.assertNotIn(serial, parser._await_queue)
        self.assertIn(serial, parser._ready_queue)
        self.assertEqual(parser._ready_queue[serial].getStatus(), self._EXPECTED_REFRESHED_STATUS)


if __name__ == "__main__":
    unittest.main()
