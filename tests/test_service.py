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
from ExpenseTracker.settings.lib import HeaderRole
from tests.base import BaseServiceTestCase


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
        # Configure unified headers list combining type info and roles
        headers_list = []
        for name, type_str in self.GOOD_HEADER.items():
            # assign role if in GOOD_MAPPING, else unmapped
            role = next((r for r, n in self.GOOD_MAPPING.items() if n == name), HeaderRole.Unmapped.value)
            headers_list.append({'name': name, 'type': type_str, 'role': role})
        lib.settings.set_section('headers', headers_list)

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

    def test_convert_types(self):
        # None cell -> string
        self.assertEqual(svc._convert_types(None), 'string')
        # Date formats
        cell_date = {'userEnteredFormat': {'numberFormat': {'type': 'DATE'}}}
        self.assertEqual(svc._convert_types(cell_date), 'date')
        # Integer numbers
        cell_int = {'userEnteredFormat': {'numberFormat': {'type': 'NUMBER'}}, 'effectiveValue': {'numberValue': 5.0}}
        self.assertEqual(svc._convert_types(cell_int), 'int')
        # Float numbers
        cell_float = {'userEnteredFormat': {'numberFormat': {'type': 'NUMBER'}}, 'effectiveValue': {'numberValue': 5.5}}
        self.assertEqual(svc._convert_types(cell_float), 'float')
        # Non-numeric and other types default to string
        cell_other = {'userEnteredFormat': {'numberFormat': {'type': 'UNKNOWN'}}}
        self.assertEqual(svc._convert_types(cell_other), 'string')
    def test_query_sheet_size(self):
        # Populate header and two rows: total rows=3 (including header)
        rows = [['2021-01-01', 'Desc', 'Cat', '', 'Acc', 1.0, 'N'] for _ in range(2)]
        self._populate_header_and_rows(rows)
        service = svc.get_service()
        # Should return row_count including header and data rows, and column_count equal to headers
        row_count, col_count = svc._query_sheet_size(service, self.sheet_id, self.sheet_name)
        self.assertEqual(row_count, 3)
        self.assertEqual(col_count, len(self.headers))
    def test_async_wrappers(self):
        # fetch_headers should mirror _fetch_headers
        self._populate_header()
        self.assertEqual(svc.fetch_headers(5), self.headers)
        # verify_headers should not raise
        svc.verify_headers(5)
        # verify_mapping should not raise
        svc.verify_mapping(5)
        # fetch_categories should mirror _fetch_categories
        rows = [['2021-01-01', 'Desc', 'CatA', '', 'Acc', 2.0, '']
                for _ in range(1)]
        self._populate_header_and_rows(rows)
        self.assertEqual(svc.fetch_categories(5), ['CatA'])
        # verify_sheet_access wrapper
        svc.verify_sheet_access(5)

    def test_idx_to_col_ranges(self):
        # Single letters
        self.assertEqual(svc.idx_to_col(0), 'A')
        self.assertEqual(svc.idx_to_col(25), 'Z')
        # Double letters
        self.assertEqual(svc.idx_to_col(26), 'AA')
        self.assertEqual(svc.idx_to_col(27), 'AB')
        self.assertEqual(svc.idx_to_col(51), 'AZ')
        self.assertEqual(svc.idx_to_col(52), 'BA')
        self.assertEqual(svc.idx_to_col(701), 'ZZ')
        # Triple letters
        self.assertEqual(svc.idx_to_col(702), 'AAA')
        self.assertEqual(svc.idx_to_col(703), 'AAB')


class ServiceContractTest(ServiceTestBase):
    """Exhaustive header/mapping contract validation (incl. merge‑mapping)."""

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

    def test_verify_mapping_success(self):
        self._populate_header()
        svc._verify_mapping()

    # New header-based mapping tests: missing singleton roles and wrong types
    def test_verify_mapping_missing_date(self):
        # Remove 'date' role entry
        headers = lib.settings.get_section('headers')
        headers = [h for h in headers if h['role'] != HeaderRole.Date.value]
        lib.settings.set_section('headers', headers)
        self._populate_header()
        with self.assertRaises(svc.status.HeaderMappingInvalidException):
            svc._verify_mapping()

    def test_verify_mapping_missing_amount(self):
        # Remove 'amount' role entry
        headers = lib.settings.get_section('headers')
        headers = [h for h in headers if h['role'] != HeaderRole.Amount.value]
        lib.settings.set_section('headers', headers)
        self._populate_header()
        with self.assertRaises(svc.status.HeaderMappingInvalidException):
            svc._verify_mapping()

    def test_verify_mapping_missing_account(self):
        # Remove 'account' role entry
        headers = lib.settings.get_section('headers')
        headers = [h for h in headers if h['role'] != HeaderRole.Account.value]
        lib.settings.set_section('headers', headers)
        self._populate_header()
        with self.assertRaises(svc.status.HeaderMappingInvalidException):
            svc._verify_mapping()

    def test_verify_mapping_wrong_date_type(self):
        # Change 'date' header to wrong type
        headers = lib.settings.get_section('headers')
        for h in headers:
            if h['role'] == HeaderRole.Date.value:
                h['type'] = 'string'
        lib.settings.set_section('headers', headers)
        self._populate_header()
        with self.assertRaises(svc.status.HeaderMappingInvalidException):
            svc._verify_mapping()

    def test_verify_mapping_wrong_amount_type(self):
        # Change 'amount' header to wrong type
        headers = lib.settings.get_section('headers')
        for h in headers:
            if h['role'] == HeaderRole.Amount.value:
                h['type'] = 'string'
        lib.settings.set_section('headers', headers)
        self._populate_header()
        with self.assertRaises(svc.status.HeaderMappingInvalidException):
            svc._verify_mapping()

    def test_verify_headers_extra_configured(self):
        # Add a configured header not present in the remote sheet
        self._populate_header()
        headers = lib.settings.get_section('headers')
        headers.append({'name': 'ExtraCol', 'type': 'string', 'role': HeaderRole.Unmapped.value})
        lib.settings.set_section('headers', headers)
        with self.assertRaises(svc.status.HeadersInvalidException):
            svc._verify_headers()


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
        # No data rows beyond header should raise SpreadsheetEmptyException
        with self.assertRaises(svc.status.SpreadsheetEmptyException):
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
