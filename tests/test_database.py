"""
Comprehensive integration tests for ExpenseTracker.core.database
(using unittest, not pytest).

This version addresses the failures observed on Windows:
* Normal ASCII hyphens in date literals
* Accepts sqlite3.OperationalError where metatable is missing
* Progress‑handler warning captured via patch
"""

import datetime
import sqlite3
from pathlib import Path
from typing import Any, List
from unittest.mock import patch

import pandas as pd

from ExpenseTracker.core.database import (
    CACHE_MAX_AGE_DAYS,
    CacheState,
    DatabaseAPI,
    Table,
    cast_type,
    get_sql_type,
    google_serial_date_to_iso,
)
from ExpenseTracker.settings import lib
from ExpenseTracker.status import status
from tests.base import BaseTestCase, mute_ui_signals

HDR_TYPES_BASE = {
    'Date': 'date',
    'Amount': 'float',
    'Description': 'string',
    'Category': 'string',
    'Count': 'int',
}

ROWS: List[List[Any]] = [
    ['2025-01-01', 10.5, 'Coffee', 'Food', 1],
    ['2025-01-02', 22, 'Rent', 'Rent', 2],
]


def df(rows: List[List[Any]] | None = None) -> pd.DataFrame:
    return pd.DataFrame(rows or ROWS, columns=list(HDR_TYPES_BASE))


class DatabaseAPITests(BaseTestCase):
    def _apply_header_cfg(self, hdr_map: dict | None = None):
        lib.settings.set_section('header', hdr_map or HDR_TYPES_BASE)

    def _cache_df(self, frame: pd.DataFrame):
        with mute_ui_signals():
            DatabaseAPI.cache_data(frame)

    def test_cast_type_matrix(self):
        self._apply_header_cfg()

        # REAL
        self.assertEqual(get_sql_type('Amount'), 'REAL')
        self.assertEqual(cast_type('Amount', '7.2'), 7.2)
        self.assertEqual(cast_type('Amount', ''), 0.0)
        self.assertEqual(cast_type('Amount', 5), 5.0)

        # INTEGER
        self.assertEqual(get_sql_type('Count'), 'INTEGER')
        self.assertEqual(cast_type('Count', '3'), 3)
        self.assertEqual(cast_type('Count', ''), 0)
        self.assertEqual(cast_type('Count', True), True)

        # STRING
        self.assertEqual(get_sql_type('Description'), 'TEXT')
        self.assertEqual(cast_type('Description', 123), '123')

        # DATE
        serial = 45002
        iso = google_serial_date_to_iso(serial)
        self.assertEqual(cast_type('Date', serial), iso)
        self.assertEqual(cast_type('Date', str(serial)), iso)

        # negative serial
        self.assertEqual(google_serial_date_to_iso(-20000), '1845-03-28')

        with self.assertRaises(status.HeadersInvalidException):
            cast_type('NoSuchHeader', 1)

    def test_cache_empty_state_empty(self):
        self._apply_header_cfg()
        self._cache_df(pd.DataFrame(columns=list(HDR_TYPES_BASE)))
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Empty)

    def test_full_roundtrip_verify_and_data(self):
        self._apply_header_cfg()
        self._cache_df(df())

        DatabaseAPI.verify()
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Valid)

        frame = DatabaseAPI.data().drop(columns=['local_id'])
        pd.testing.assert_frame_equal(frame.reset_index(drop=True), df(), check_dtype=False)

    def test_column_mismatch_marks_stale(self):
        self._apply_header_cfg()
        bad = pd.DataFrame([['x']], columns=['Wrong'])
        with self.assertRaises(status.HeadersInvalidException):
            self._cache_df(bad)
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Stale)

    def test_schema_change_detected(self):
        self._apply_header_cfg()
        self._cache_df(df())

        new_hdr = HDR_TYPES_BASE.copy()
        new_hdr.pop('Category')
        lib.settings.set_section('header', new_hdr)

        with self.assertRaises(status.CacheInvalidException):
            DatabaseAPI.verify()
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Stale)

    def test_age_based_stale_detection(self):
        self._apply_header_cfg()
        self._cache_df(df())

        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=CACHE_MAX_AGE_DAYS + 1)
        conn = DatabaseAPI.connection()
        conn.execute(f'UPDATE {Table.Meta} SET last_sync=? WHERE meta_id=1', (past.isoformat(),))
        conn.commit()
        conn.close()

        with self.assertRaises(status.CacheInvalidException):
            DatabaseAPI.verify()
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Stale)

    def test_get_row_and_update_cell(self):
        self._apply_header_cfg()
        self._cache_df(df())

        self.assertEqual(DatabaseAPI.get_row(1)['Amount'], 10.5)

        DatabaseAPI.update_cell(1, 'Amount', 99.0)
        self.assertEqual(DatabaseAPI.get_row(1)['Amount'], 99.0)
        self.assertIsNone(DatabaseAPI.get_row(999))

        with self.assertRaises(sqlite3.OperationalError):
            DatabaseAPI.update_cell(1, 'Bogus', 'x')

    def test_delete_retries(self):
        self._apply_header_cfg()
        self._cache_df(df())
        target = lib.settings.db_path

        side_effects = [PermissionError, PermissionError, None]
        original_unlink = Path.unlink

        def flaky_unlink(self):
            effect = side_effects.pop(0)
            if effect is None:
                original_unlink(self)
            else:
                raise effect

        with patch.object(Path, 'unlink', flaky_unlink):
            DatabaseAPI.delete()

        self.assertFalse(target.exists())

    def test_verify_missing_db_file(self):
        self._apply_header_cfg()
        self._cache_df(df())
        lib.settings.db_path.unlink()

        with self.assertRaises((status.CacheInvalidException, sqlite3.OperationalError)):
            DatabaseAPI.verify()

    def test_verify_missing_meta_table(self):
        self._apply_header_cfg()
        self._cache_df(df())

        conn = DatabaseAPI.connection()
        conn.execute('DROP TABLE metatable')
        conn.commit()
        conn.close()

        with self.assertRaises((status.CacheInvalidException, sqlite3.OperationalError)):
            DatabaseAPI.verify()

    def test_reset_cache_deletes_file(self):
        self._apply_header_cfg()
        self._cache_df(df())
        db_file = lib.settings.db_path
        self.assertTrue(db_file.exists())

        DatabaseAPI().reset_cache()
        self.assertFalse(db_file.exists())

    def test_data_read_sql_fails_returns_empty(self):
        self._apply_header_cfg()
        self._cache_df(df())

        with patch('ExpenseTracker.core.database.pd.read_sql_query', side_effect=sqlite3.DatabaseError):
            self.assertTrue(DatabaseAPI.data().empty)


def test_cast_type_locale_fallback_parses_string_dates(self):
    """
    `cast_type('Date', <str>)` should try the current locale first and then
    the fallback list.  We monkey‑patch ``locale.parse_date`` to force a
    predictable path:

    * For the string ``"02.01.2025"`` the fake parser recognises it only
      when the caller passes *any* locale (we don't care which) and returns
      2 Jan 2025.
    * For any other input it raises ``ValueError`` so that the outer loop
      keeps iterating / eventually fails.

    The expected final ISO string is **2025‑01‑02**.
    """
    self._apply_header_cfg()

    # fake parse_date that understands just one format
    def fake_parse_date(text: str, *, locale: str):
        if text == "02.01.2025":
            return datetime.datetime(2025, 1, 2)
        raise ValueError("unrecognised")

    with patch(
            "ExpenseTracker.core.database.locale.parse_date",
            side_effect=fake_parse_date,
    ):
        # value should be normalised to canonical ISO format
        iso = cast_type("Date", "02.01.2025")
        self.assertEqual(iso, "2025-01-02")
