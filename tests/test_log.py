# tests/test_log.py
"""
Integration tests for ExpenseTracker.core.log
(covers TankHandler, Qt bridge, setup helpers – plus simple performance checks).

Run:
    python -m unittest tests.test_log
"""
import logging
import time
from typing import List

from PySide6.QtCore import QtMsgType

from ExpenseTracker.log.log import (
    TankHandler,
    qt_message_handler,
    set_logging_level,
    setup_logging,
)
from ExpenseTracker.ui.actions import signals
from tests.base import BaseTestCase


class LogModuleTests(BaseTestCase):
    """
    Each test starts with a fresh root logger configured by
    setup_logging(enable_stream_handler=False).
    """

    def setUp(self) -> None:
        super().setUp()

        # enable logging
        logging.disable(logging.NOTSET)

        setup_logging(enable_stream_handler=False,
                      enable_qt_handler=False,
                      log_level=logging.DEBUG)

        self.root_logger = logging.getLogger()
        self.tank: TankHandler = next(
            h for h in self.root_logger.handlers if isinstance(h, TankHandler)
        )

    def test_tank_bulk_append_speed(self):
        """
        Appending thousands of records should be quick and all must be stored.
        """
        self.tank.clear_logs()
        N = 10_000
        t0 = time.perf_counter()
        for i in range(N):
            logging.debug("bulk‑%05d", i)
        elapsed = time.perf_counter() - t0

        self.assertLessEqual(
            elapsed, 1.0,
            f"logging {N} messages took {elapsed:.2f}s, expected ≤1 s",
        )
        self.assertEqual(len(self.tank.tank), N)

    def test_tank_handles_very_long_message(self):
        """
        A very long error message is stored intact and still raises the showLogs signal.
        """
        long_msg = "X" * 100_000  # 100 kB payload
        triggered: list[bool] = []

        def _slot() -> None:
            triggered.append(True)

        signals.showLogs.connect(_slot)
        try:
            logging.error(long_msg)
        finally:
            signals.showLogs.disconnect(_slot)

        self.assertTrue(triggered, "showLogs not emitted for long ERROR message")
        stored = self.tank.get_logs(logging.ERROR)[-1]
        # The formatted record includes date/module etc.; ensure payload is present
        self.assertIn(long_msg[-50:], stored[-60:], "Long message truncated in TankHandler")

    def test_set_logging_level_accepts_valid_levels(self):
        set_logging_level(logging.ERROR)
        self.assertEqual(self.root_logger.level, logging.ERROR)
        for h in self.root_logger.handlers:
            self.assertEqual(h.level, logging.ERROR)

    def test_set_logging_level_rejects_non_int(self):
        with self.assertRaises(ValueError):
            set_logging_level("INFO")  # type: ignore[arg-type]

    def test_set_logging_level_rejects_unknown(self):
        with self.assertRaises(ValueError):
            set_logging_level(1234)

    def test_tank_handler_stores_and_filters(self):
        logging.debug("dbg message")
        logging.error("err message")
        self.assertEqual(len(self.tank.tank), 2)
        errs: List[str] = self.tank.get_logs(logging.ERROR)
        self.assertEqual(len(errs), 1)
        self.assertIn("err message", errs[0])
        self.tank.clear_logs()
        self.assertEqual(len(self.tank.tank), 0)

    def test_emit_triggers_showLogs_on_error(self):
        triggered: list[bool] = []

        def _slot() -> None:
            triggered.append(True)

        signals.showLogs.connect(_slot)
        try:
            logging.error("should emit signal")
            self.assertTrue(triggered)
        finally:
            signals.showLogs.disconnect(_slot)

    def test_qt_message_handler_maps_to_logging(self):
        qt_message_handler(QtMsgType.QtInfoMsg, None, "Qt info")
        qt_message_handler(QtMsgType.QtWarningMsg, None, "Qt warn")
        msgs = self.tank.get_logs()
        self.assertTrue(any("Qt info" in m for m in msgs))
        self.assertTrue(any("Qt warn" in m for m in msgs))

    def test_qt_message_handler_fatal_exits(self):
        with self.assertRaises(SystemExit):
            qt_message_handler(QtMsgType.QtFatalMsg, None, "fatal")

    def test_setup_logging_installs_tank_handler_only(self):
        self.assertEqual(
            [type(h) for h in self.root_logger.handlers],
            [TankHandler],
        )
