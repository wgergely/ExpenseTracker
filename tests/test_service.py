"""Integration + contract tests for ExpenseTracker.core.service.

Live Google‑Sheets workbook, no mocks.  Three test cases:

* ServiceHelpersTest       – quick smoke checks on the sync helpers
* ServiceContractTest      – exhaustive header/mapping (incl. merge‑mapping)
* ServiceDataIntegrityTest – big + messy data fetch / pagination
"""
from datetime import datetime, timedelta
from random import choice, randint
from typing import Any, Dict, List, Optional

from ExpenseTracker.core import service as svc
from ExpenseTracker.settings import lib
from tests.base import BaseServiceTestCase


# --------------------------------------------------------------------------- shared base
class ServiceTestBase(BaseServiceTestCase):
    """Common helpers and canonical valid schema."""

    GOOD_HEADER: Dict[str, str] = {
        'Date': 'date',
        'Description': 'string',
        'Category': 'string',
        'SubCategory': 'string',  # needed for merge‑mapping tests
        'Account': 'string',
        'Amount': 'float',
        'Notes': 'string',
    }
    GOOD_MAPPING: Dict[str, str] = {
        'date': 'Date',
        'description': 'Description',
        'category': 'Category',
        'account': 'Account',
        'amount': 'Amount',
    }

    def setUp(self) -> None:
        super().setUp()
        lib.settings.set_section('header', self.GOOD_HEADER)
        lib.settings.set_section('mapping', self.GOOD_MAPPING)

        cfg = lib.settings.get_section('spreadsheet')
        self.sheet_id, self.sheet_name = cfg['id'], cfg['worksheet']
        self.service = svc.get_service()

        self._wipe_remote_sheet()

        self.headers: List[str] = list(self.GOOD_HEADER.keys())

    def tearDown(self) -> None:
        try:
            self._wipe_remote_sheet()
        finally:
            super().tearDown()

    # ---------------- remote sheet helpers -----------------------------
    def _wipe_remote_sheet(self) -> None:
        self.service.spreadsheets().values().clear(
            spreadsheetId=self.sheet_id, range=self.sheet_name, body={}
        ).execute()

    def _write_rows(self, rows: List[List[Any]], start: str = 'A1') -> None:
        self.service.spreadsheets().values().update(
            spreadsheetId=self.sheet_id,
            range=f'{self.sheet_name}!{start}',
            valueInputOption='USER_ENTERED',
            body={'values': rows},
        ).execute()

    def _populate_header(self, header: Optional[List[str]] = None) -> None:
        self._write_rows([header or self.headers])

    def _populate_header_and_rows(self, rows: List[List[Any]]) -> None:
        self._write_rows([self.headers] + rows)


# --------------------------------------------------------------------------- 1. helper smoke tests
class ServiceHelpersTest(ServiceTestBase):
    """Basic ‘does not crash’ checks."""

    def test_verify_sheet_access_ok(self):
        svc._verify_sheet_access()

    def test_fetch_headers(self):
        self._populate_header()
        self.assertEqual(svc._fetch_headers(), self.headers)

    def test_fetch_data_basic(self):
        rows = [
            ['2023‑01‑01', 'Groceries', 'Food', 'Grocery', 'Cash', 75.40, 'note'],
            ['2023‑01‑02', 'Rent', 'Rent', 'Housing', 'Checking', 750, 'note'],
        ]
        self._populate_header_and_rows(rows)
        df = svc._fetch_data()
        self.assertEqual(df.shape, (2, len(self.headers)))
        self.assertListEqual(list(df.columns), self.headers)

    def test_fetch_categories_sorted_unique(self):
        rows = [
            ['2023‑01‑01', 'Lunch', 'b‑cat', '', 'Cash', 12, '‑'],
            ['2023‑01‑02', 'ISP', 'a‑cat', '', 'Credit', 40, '‑'],
            ['2023‑01‑03', 'Lunch', 'b‑cat', '', 'Cash', 14, '‑'],
        ]
        self._populate_header_and_rows(rows)
        self.assertEqual(svc._fetch_categories(), ['a‑cat', 'b‑cat'])


# --------------------------------------------------------------------------- 2. contract tests
class ServiceContractTest(ServiceTestBase):
    """Exhaustive header/mapping contract validation (incl. merge‑mapping)."""

    # ---------- header presence / duplication --------------------------
    def test_verify_headers_success(self):
        self._populate_header()
        self.assertEqual(svc._verify_headers(), set(self.headers))

    def test_verify_headers_missing_required(self):
        bad_header = [h for h in self.headers if h != 'Description']
        self._populate_header(bad_header)
        with self.assertRaises(svc.status.HeadersInvalidException):
            svc._verify_headers()

    def test_verify_headers_duplicate_names_ok(self):
        dup = self.headers + ['Category']
        self._populate_header(dup)
        self.assertTrue(set(self.headers).issubset(svc._verify_headers()))

    # ---------- mapping key presence -----------------------------------
    def testverify_mapping_success(self):
        self._populate_header()
        svc._verify_mapping()

    def _install_mapping(self, mapping: Dict[str, str]):
        lib.settings.set_section('mapping', mapping)

    def testverify_mapping_missing_date_key(self):
        # Missing required mapping key should be rejected by settings
        mapping = dict(self.GOOD_MAPPING)
        mapping.pop('date')
        with self.assertRaises(ValueError):
            self._install_mapping(mapping)

    def testverify_mapping_missing_amount_key(self):
        # Missing required mapping key should be rejected by settings
        mapping = dict(self.GOOD_MAPPING)
        mapping.pop('amount')
        with self.assertRaises(ValueError):
            self._install_mapping(mapping)

    def testverify_mapping_missing_account_key(self):
        # Missing required mapping key should be rejected by settings
        mapping = dict(self.GOOD_MAPPING)
        mapping.pop('account')
        with self.assertRaises(ValueError):
            self._install_mapping(mapping)

    # ---------- mapping wrong reference / type -------------------------
    def testverify_mapping_unknown_column_reference(self):
        bad_map = {**self.GOOD_MAPPING, 'account': 'NonExistent'}
        self._install_mapping(bad_map)
        self._populate_header()
        with self.assertRaises(svc.status.HeaderMappingInvalidException):
            svc._verify_mapping()

    def testverify_mapping_wrong_amount_type(self):
        bad_header = {**self.GOOD_HEADER, 'Amount': 'string'}
        lib.settings.set_section('header', bad_header)
        self._populate_header(list(bad_header.keys()))
        with self.assertRaises(svc.status.HeaderMappingInvalidException):
            svc._verify_mapping()

    # ---------- merge-mapping (only allowed on 'description') ------------
    def test_merge_mapping_on_description_success(self):
        # Only 'description' may map to multiple columns
        merge_map = dict(self.GOOD_MAPPING)
        merge_map['description'] = 'Description|Notes'
        self._install_mapping(merge_map)
        self._populate_header()
        svc._verify_mapping()

    def test_merge_mapping_on_description_missing_remote_column(self):
        merge_map = dict(self.GOOD_MAPPING)
        merge_map['description'] = 'Description|NonExistent'
        self._install_mapping(merge_map)
        self._populate_header()
        with self.assertRaises(svc.status.HeaderMappingInvalidException):
            svc._verify_mapping()

    def test_merge_mapping_on_other_key_disallowed(self):
        # Multi-mapping on any key other than 'description' should be rejected by settings
        bad_map = dict(self.GOOD_MAPPING)
        bad_map['category'] = 'Category|SubCategory'
        with self.assertRaises(ValueError):
            self._install_mapping(bad_map)

    # ---------- duplicate mappings disallowed ---------------------------
    def test_mapping_duplicate_values_disallowed(self):
        # Mapping must not contain extra keys or duplicate references
        dup_map = dict(self.GOOD_MAPPING)
        dup_map['amount_copy'] = 'Amount'
        with self.assertRaises(ValueError):
            self._install_mapping(dup_map)


# --------------------------------------------------------------------------- 3. data integrity tests
class ServiceDataIntegrityTest(ServiceTestBase):
    """Large & messy datasets including pagination."""

    def test_fetch_data_large_batch(self):
        self._populate_header()
        today = datetime.utcnow().date()
        rows = [
            [str(today - timedelta(days=i)), f'Desc {i}', choice(['Food', 'Rent']),
             choice(['Sub1', 'Sub2']), choice(['Cash', 'Credit']),
             randint(1, 250), '‑']
            for i in range(svc.BATCH_SIZE + 25)
        ]
        self._write_rows(rows, start='A2')
        df = svc._fetch_data()
        self.assertEqual(len(df), svc.BATCH_SIZE + 25)

    def test_fetch_categories_no_data_raises(self):
        self._populate_header()
        with self.assertRaises(svc.status.UnknownException):
            svc._fetch_categories()

    def test_fetch_data_with_missing_and_mixed_values(self):
        rows = [
            ['2023-01-01', '', 'Food', '', 'Cash', '', '-'],
            ['', 'Late fee', 'Rent', '', 'Credit', 50, '-'],
            ['bad-date', 'Oops', '', '', '', 'oops', '-'],
        ]
        self._populate_header_and_rows(rows)
        df = svc._fetch_data()
        # shape should reflect all rows, but empty or invalid values remain as-is
        self.assertEqual(df.shape[0], 3)
        self.assertFalse(df.isna().any(axis=None))
