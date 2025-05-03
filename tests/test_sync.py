"""Full‑spectrum tests for ExpenseTracker.core.sync.

Two test‑case classes are included:

1. **SyncIntegrationTest**
   – live Google‑Sheets integration via BaseServiceTestCase

2. **SyncInternalHelperTest**
   – pure‑Python unit tests for every private helper, using lightweight stubs
"""
import itertools
import random
import types
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import pandas as pd

from ExpenseTracker.core.database import DatabaseAPI
from ExpenseTracker.core.sync import EditOperation, SyncAPI
from ExpenseTracker.settings import lib
from tests.base import BaseTestCase, BaseServiceTestCase, mute_ui_signals


def gen_rows(n: int, *, with_id: bool = True, dup: bool = False) -> List[List[Any]]:
    """Return *n* ledger rows (optionally duplicate stable keys)."""
    cat_pool, note_pool, acc_pool = ['Food', 'Rent', 'Fuel', 'Fun'], ['N1', 'N2', 'N3'], ['Cash', 'Checking', 'Credit']
    rows: List[List[Any]] = []
    for i in range(n):
        rid = i + 1
        date = f'2025-01-{(i % 28) + 1:02d}'
        desc = f'Desc{rid}' if not dup else 'Dup'
        notes, amt, cat, acc = random.choice(note_pool), float((i * 3) % 157) + 0.5, random.choice(
            cat_pool) if not dup else 'DupCat', acc_pool[i % 3]
        row = [rid] if with_id else []
        row += [date, desc, cat, notes, acc, amt]
        rows.append(row)
    return rows


class SyncIntegrationTest(BaseServiceTestCase):
    """Live‑sheet integration tests covering optimistic‑lock behaviour."""

    HDR_ALL = ['ID', 'Date', 'Description', 'Category', 'Notes', 'Account', 'Amount']
    HDR_NO_ID = ['Date', 'Description', 'Category', 'Notes', 'Account', 'Amount']
    MAP_BASE = {
        'date': 'Date',
        'description': 'Description|Notes',
        'category': 'Category',
        'account': 'Account',
        'amount': 'Amount',
    }

    def setUp(self) -> None:
        super().setUp()
        from ExpenseTracker.core.service import get_service
        self.service = get_service()
        cfg = lib.settings.get_section('spreadsheet')
        self.sheet_id, self.sheet_name = cfg['id'], cfg['worksheet']

    def tearDown(self) -> None:
        self.service.spreadsheets().values().clear(
            spreadsheetId=self.sheet_id, range=self.sheet_name, body={}
        ).execute()
        super().tearDown()

    def _setup_sheet_and_cache(self, header: List[str], mapping: Dict[str, str], rows: List[List[Any]]):
        hdr_types = {h: ('int' if h in {'ID', '#'}
                         else 'float' if h == 'Amount'
        else 'date' if h == 'Date'
        else 'string') for h in header}
        lib.settings.set_section('header', hdr_types)
        lib.settings.set_section('mapping', mapping)

        df = pd.DataFrame(rows, columns=header)
        with mute_ui_signals():
            DatabaseAPI.cache_data(df)

        self.service.spreadsheets().values().update(
            spreadsheetId=self.sheet_id,
            range=f'{self.sheet_name}!A1',
            valueInputOption='USER_ENTERED',
            body={'values': [header] + rows},
        ).execute()

    def _run_commit(self, local_id: int, column: str, new_val: Any):
        sync = SyncAPI()
        sync.queue_edit(local_id, column, new_val)
        with mute_ui_signals():
            return sync.commit_queue()

    # ---------------------------------------------------------------- integration scenarios
    def test_commit_all_columns_large_dataset(self):
        rows = gen_rows(1_000)
        self._setup_sheet_and_cache(self.HDR_ALL, self.MAP_BASE, rows)

        edits = [(500, 'description', 'EditedDesc'),
                 (600, 'amount', 999.99),
                 (700, 'category', 'EditedCat'),
                 (800, 'account', 'EditedAcc'),
                 (900, 'date', '2025-02-28')]

        sync = SyncAPI()
        for lid, col, val in edits:
            sync.queue_edit(lid, col, val)
        with mute_ui_signals():
            res = sync.commit_queue()

        for lid, col, _ in edits:
            ok, msg = res[(lid, col)]
            self.assertTrue(ok, msg)

    def test_merge_mapping_description_updates_first_header(self):
        rows = gen_rows(2)
        self._setup_sheet_and_cache(self.HDR_ALL, self.MAP_BASE, rows)
        new_desc = 'NewDesc'
        self.assertTrue(self._run_commit(1, 'description', new_desc)[(1, 'description')][0])
        val = self.service.spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range=f'{self.sheet_name}!C2').execute()['values'][0][0]
        self.assertEqual(val, new_desc)

    def test_id_alias_hash_header(self):
        hdr = ['#'] + self.HDR_ALL[1:]
        rows = gen_rows(3)
        for r, rid in zip(rows, itertools.count(1)):
            r[0] = rid
        self._setup_sheet_and_cache(hdr, self.MAP_BASE, rows)
        self.assertTrue(self._run_commit(2, 'amount', 123.45)[(2, 'amount')][0])

    def test_ambiguous_without_id_resolves_by_row_order(self):
        rows = gen_rows(4, with_id=False, dup=True)
        self._setup_sheet_and_cache(self.HDR_NO_ID, self.MAP_BASE, rows)
        self.assertTrue(self._run_commit(1, 'amount', 55.0)[(1, 'amount')][0])

    def test_remote_changed_after_cache_no_match_without_id(self):
        rows = gen_rows(2, with_id=False)
        self._setup_sheet_and_cache(self.HDR_NO_ID, self.MAP_BASE, rows)
        # mutate stable key
        self.service.spreadsheets().values().update(
            spreadsheetId=self.sheet_id,
            range=f'{self.sheet_name}!F2', valueInputOption='USER_ENTERED',
            body={'values': [[999]]}).execute()
        ok, msg = self._run_commit(1, 'description', 'X')[(1, 'description')]
        self.assertFalse(ok)
        self.assertIn('No matching row', msg)

    def test_queue_edit_unknown_id_raises(self):
        self._setup_sheet_and_cache(self.HDR_ALL, self.MAP_BASE, gen_rows(1))
        sync = SyncAPI()
        with self.assertRaises(ValueError):
            sync.queue_edit(999, 'amount', 1.0)

    def test_batch_update_http_error_sets_failure(self):
        """If batchUpdate hits an HTTP 403, SyncAPI should mark the edit as failed."""
        rows = gen_rows(1)
        self._setup_sheet_and_cache(self.HDR_ALL, self.MAP_BASE, rows)

        sync = SyncAPI()
        sync.queue_edit(1, 'amount', 9.0)

        from googleapiclient.http import HttpRequest
        from googleapiclient.errors import HttpError
        from httplib2 import Response

        orig_execute = HttpRequest.execute  # keep original impl

        def execute_maybe_raise(self, *args, **kwargs):
            # raise only for the final write request
            if getattr(self, "methodId", "") == "sheets.spreadsheets.values.batchUpdate":
                raise HttpError(Response({"status": 403}), b"forbidden")
            return orig_execute(self, *args, **kwargs)

        with patch.object(HttpRequest, "execute", execute_maybe_raise):
            with mute_ui_signals():
                result = sync.commit_queue()

        ok, msg = result[(1, "amount")]
        self.assertFalse(ok)
        self.assertIn("HTTPError", msg)


# --------------------------------------------------------------------------- stub‑service builder
def _make_service(headers: List[str], col_vals: Dict[Tuple[str, str], List[Any]]):
    """
    Return a stub object that mimics the chained
        service.spreadsheets().values().{get|batchGet}(...).execute()
    pattern used by SyncAPI.  Each terminal call returns an object with
    an .execute() method so the production code works unchanged.
    """

    class _Exec:
        def __init__(self, payload: Dict[str, Any]):
            self._payload = payload

        def execute(self):
            return self._payload

    class _Values:
        def __init__(self, hdrs: List[str], data: Dict[Tuple[str, str], List[Any]]):
            self._hdrs = hdrs
            self._data = data

        def get(self, **kw):
            rng = kw.get("range", "")
            if rng.endswith("1"):
                return _Exec({"values": [self._hdrs]})
            return _Exec({})  # not used elsewhere

        def batchGet(self, **kw):
            vrs = []
            for rng in kw["ranges"]:
                if rng.endswith("1"):
                    vrs.append({"values": [self._hdrs]})
                else:
                    col_letter = rng.split("!")[1][0]
                    hdr = self._hdrs[ord(col_letter) - ord("A")]
                    logical = next(l for (l, h) in self._data if h == hdr)
                    vrs.append({"values": [[v] for v in self._data[(logical, hdr)]]})
            return _Exec({"valueRanges": vrs})

    class _Sheets:
        def __init__(self, hdrs, data):
            self._values = _Values(hdrs, data)

        def values(self):
            return self._values

    return types.SimpleNamespace(spreadsheets=lambda: _Sheets(headers, col_vals))


class SyncInternalHelperTest(BaseTestCase):
    """Pure‑python unit tests for every private helper inside SyncAPI."""

    def setUp(self) -> None:
        super().setUp()
        self.sync = SyncAPI()

        # Provide a *complete* header / mapping so SettingsAPI validation
        # succeeds.
        lib.settings.set_section(
            "header",
            {
                "ID": "int",
                "Date": "date",
                "Amount": "float",
                "Description": "string",
                "Notes": "string",
                "Category": "string",
                "Account": "string",
            },
        )

        lib.settings.set_section(
            "mapping",
            {
                "date": "Date",
                "amount": "Amount",
                "description": "Description|Notes",
                "category": "Category",
                "account": "Account",
            },
        )

    # _get_parsed_mapping -----------------------------------------------------
    def test_parsed_mapping_split_and_cache(self):
        first = self.sync._get_parsed_mapping('description')
        self.assertEqual(first, ['Description', 'Notes'])

        # update mapping but keep required keys so validator passes
        mapping = lib.settings.get_section('mapping')
        mapping['description'] = 'X'
        lib.settings.set_section('mapping', mapping)

        # cache should still return the original parsed list
        self.assertIs(first, self.sync._get_parsed_mapping('description'))

    # _get_local_stable_keys --------------------------------------------------
    def test_local_stable_keys_extraction(self):
        row = {'ID': 7, 'Date': '2025-01-01', 'Amount': 10,
               'Description': 'Foo', 'Notes': 'Bar'}
        keys = self.sync._get_local_stable_keys(row)
        self.assertEqual(keys, {
            'date': ('2025-01-01',),
            'amount': (10,),
            'description': ('Foo', 'Bar'),
            'id': (7,),
        })

    # _get_original_value -----------------------------------------------------
    def test_get_original_value_prefers_first_mapping_hit(self):
        row = {'Description': 'Foo', 'Notes': 'Bar'}
        self.assertEqual(self.sync._get_original_value(row, 'description'), 'Foo')

    # _fetch_headers ----------------------------------------------------------
    def test_fetch_headers_returns_header_row(self):
        service = _make_service(['A', 'B'], {})
        self.assertEqual(self.sync._fetch_headers(service, 2), ['A', 'B'])

    # _determine_stable_fields ------------------------------------------------
    def test_determine_stable_fields_prefers_id(self):
        self.assertEqual(self.sync._determine_stable_fields(['ID', 'X']), ['id'])

    # _build_stable_headers_map ----------------------------------------------
    def test_build_stable_headers_map_error(self):
        with self.assertRaises(ValueError):
            self.sync._build_stable_headers_map(['Date'], ['description'])

    # _fetch_stable_data, _assemble_remote_rows, _build_remote_index_map -----
    def test_data_roundtrip_helpers(self):
        headers = ['ID', 'Date', 'Amount']
        col_vals = {
            ('id', 'ID'): ['1'],
            ('date', 'Date'): [45227],  # 2023‑10‑28 serial
            ('amount', 'Amount'): ['10.23'],
        }
        svc = _make_service(headers, col_vals)
        idx = {h: i for i, h in enumerate(headers)}
        stable_map = {'id': ['ID'], 'date': ['Date'], 'amount': ['Amount']}
        fetched = self.sync._fetch_stable_data(svc, stable_map, idx, 2, 1)
        self.assertEqual(fetched[('amount', 'Amount')][0], 10.23)

        rows = self.sync._assemble_remote_rows(fetched, ['id', 'date', 'amount'], 1)
        m = self.sync._build_remote_index_map(rows, ['id', 'date', 'amount'])
        self.assertIn(((1,), ('2023-10-28',), (10.23,)), m)

    # _match_operations, _build_update_payload, _apply_local_updates ---------
    @patch('ExpenseTracker.core.sync.DatabaseAPI.update_cell')
    def test_match_and_payload_and_apply(self, mock_update):
        self.sync._queue = [EditOperation(1, 'amount', 1, 2,
                                          {'date': ('d',), 'amount': (1,), 'description': ('x',)})]
        idx_map = {(('d',), (1,), ('x',)): [0]}
        results = {}
        to_upd = self.sync._match_operations(idx_map, ['date', 'amount', 'description'], results)
        payload = self.sync._build_update_payload(to_upd, {'Amount': 1})
        self.assertEqual(payload['data'][0]['values'][0][0], 2)
        self.sync._apply_local_updates(to_upd, {'Amount': 1})
        mock_update.assert_called_once_with(1, 'Amount', 2)
