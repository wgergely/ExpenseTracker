import datetime
import sqlite3
from pathlib import Path
from typing import Any, List
from unittest.mock import patch

import pandas as pd
import unittest

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

class DatabaseAPITestSuite(BaseTestCase):
    """
    Integration tests for DatabaseAPI using the live 'headers' section from settings.lib.
    Dynamically builds test data frames based on the current ledger schema.
    """

    def setUp(self):
        # Load and re-apply the headers configuration from settings
        self.headers = lib.settings.get_section('headers')
        lib.settings.set_section('headers', self.headers)
        # Column names and role→name mapping
        self.col_names = [h['name'] for h in self.headers]
        self.role_map = {h['role']: h['name'] for h in self.headers}
        # Build two sample rows matching types
        row1, row2 = [], []
        for h in self.headers:
            typ = h['type']
            if typ == 'date':
                row1.append('2025-01-01'); row2.append('2025-01-02')
            elif typ == 'float':
                row1.append(10.5); row2.append(20.75)
            elif typ == 'int':
                row1.append(1); row2.append(2)
            else:
                row1.append('foo'); row2.append('bar')
        self.sample_rows = [row1, row2]

    def make_df(self, rows: List[List[Any]] = None) -> pd.DataFrame:
        return pd.DataFrame(rows or self.sample_rows, columns=self.col_names)

    def cache(self, df: pd.DataFrame) -> None:
        with mute_ui_signals():
            DatabaseAPI.cache_data(df)

    def test_type_casting_and_sql_types(self):
        # Test SQL type mapping
        for role, expected in [('amount','REAL'), ('date','TEXT'), ('category','TEXT')]:
            name = self.role_map.get(role)
            if name:
                self.assertEqual(get_sql_type(name), expected)
        # Test cast_type and google_serial_date_to_iso
        date_col = self.role_map.get('date')
        serial = 45002
        iso = google_serial_date_to_iso(serial)
        self.assertEqual(cast_type(date_col, serial), iso)
        self.assertEqual(cast_type(date_col, str(serial)), iso)

        amt_col = self.role_map.get('amount')
        self.assertEqual(cast_type(amt_col, '7.2'), 7.2)

        count_col = self.role_map.get('id') or self.role_map.get('count')
        if count_col:
            self.assertEqual(cast_type(count_col, '3'), 3)

        # Unknown header
        with self.assertRaises(status.HeadersInvalidException):
            cast_type('NoSuchHeader', 0)

    def test_empty_dataframe(self):
        df_empty = pd.DataFrame(columns=self.col_names)
        self.cache(df_empty)
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Empty)
        self.assertTrue(DatabaseAPI.data().empty)

    def test_full_cycle_verify_and_read(self):
        df = self.make_df()
        self.cache(df)
        DatabaseAPI.verify()
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Valid)
        out = DatabaseAPI.data().drop(columns=['local_id'])
        pd.testing.assert_frame_equal(out.reset_index(drop=True), df, check_dtype=False)

    def test_column_mismatch(self):
        bad = pd.DataFrame([[1,2,3]], columns=['X','Y','Z'])
        with self.assertRaises(status.HeadersInvalidException):
            self.cache(bad)
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Stale)

    def test_schema_change(self):
        df = self.make_df()
        self.cache(df)
        # Remove last header
        new_headers = self.headers[:-1]
        lib.settings.set_section('headers', new_headers)
        with self.assertRaises(status.CacheInvalidException):
            DatabaseAPI.verify()
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Stale)

    def test_stale_by_age(self):
        df = self.make_df()
        self.cache(df)
        past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=CACHE_MAX_AGE_DAYS+1)
        conn = DatabaseAPI.connection()
        conn.execute(f'UPDATE {Table.Meta.value} SET last_sync=? WHERE meta_id=1', (past.isoformat(),))
        conn.commit(); conn.close()
        with self.assertRaises(status.CacheInvalidException):
            DatabaseAPI.verify()
        self.assertEqual(DatabaseAPI.get_state(), CacheState.Stale)

    def test_get_row_and_update(self):
        df = self.make_df()
        self.cache(df)
        amount = DatabaseAPI.get_row(1)[self.role_map['amount']]
        self.assertEqual(amount, 10.5)
        DatabaseAPI.update_cell(1, self.role_map['amount'], 99.0)
        self.assertEqual(DatabaseAPI.get_row(1)[self.role_map['amount']], 99.0)
        self.assertIsNone(DatabaseAPI.get_row(999))
        with self.assertRaises(sqlite3.OperationalError):
            DatabaseAPI.update_cell(1, 'Bogus', 0)

    def test_delete_and_reset(self):
        df = self.make_df()
        self.cache(df)
        db_file = lib.settings.db_path
        # flaky delete
        side = [PermissionError, PermissionError, None]
        orig = Path.unlink
        def flaky(self):
            e = side.pop(0)
            if e: raise e
            return orig(self)
        with patch.object(Path, 'unlink', flaky):
            DatabaseAPI.delete()
        self.assertFalse(db_file.exists())
        # reset_cache
        self.cache(self.make_df())
        DatabaseAPI().reset_cache()
        self.assertFalse(db_file.exists())

    def test_missing_db_and_meta(self):
        df = self.make_df()
        self.cache(df)
        lib.settings.db_path.unlink()
        with self.assertRaises(Exception): DatabaseAPI.verify()
        self.cache(self.make_df())
        conn = DatabaseAPI.connection()
        conn.execute(f'DROP TABLE {Table.Meta.value}'); conn.commit(); conn.close()
        with self.assertRaises(Exception): DatabaseAPI.verify()

    def test_data_read_sql_error(self):
        df = self.make_df()
        self.cache(df)
        with patch('ExpenseTracker.core.database.pd.read_sql_query', side_effect=sqlite3.DatabaseError):
            self.assertTrue(DatabaseAPI.data().empty)

class LocaleFallbackTest(unittest.TestCase):
    def test_date_string_fallback(self):
        def fake_parse(text: str, *, locale: str):
            if text == '02.01.2025': return datetime.datetime(2025,1,2)
            raise ValueError
        with patch('ExpenseTracker.core.database.locale.parse_date', side_effect=fake_parse):
            date_col = lib.settings.get_section('headers')[0]['name']  # assuming first is date
            result = cast_type(date_col, '02.01.2025')
            self.assertEqual(result, '2025-01-02')

if __name__ == '__main__':
    unittest.main()
