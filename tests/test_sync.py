"""
Unit tests for sync.py module, covering main and private functions of SyncManager.
"""
import unittest
from unittest.mock import patch, MagicMock

from ExpenseTracker.core import sync as sync_mod
from ExpenseTracker.core.sync import SyncManager, EditOperation, _idx_to_col


class TestSyncModule(unittest.TestCase):
    """Tests for SyncManager and related helper functions."""

    def setUp(self):
        # Initialize a fresh SyncManager for each test
        self.manager = SyncManager()
        # Stub out mapping parser to identity mapping
        parse_p = patch('ExpenseTracker.core.sync.parse_mapping_spec', side_effect=lambda spec: [spec])
        self.mock_parse = parse_p.start()
        self.addCleanup(parse_p.stop)
        # Stub out settings mapping lookup
        settings_p = patch('ExpenseTracker.core.sync.lib.settings.get_section', return_value={})
        self.mock_settings = settings_p.start()
        self.addCleanup(settings_p.stop)
        # Stub out external mapping verification
        verify_p = patch('ExpenseTracker.core.sync._verify_mapping', return_value=None)
        self.mock_verify = verify_p.start()
        self.addCleanup(verify_p.stop)

    def test_idx_to_col_basic(self):
        # Test conversion of column indices to spreadsheet letters
        cases = {
            0: 'A', 25: 'Z', 26: 'AA', 27: 'AB',
            51: 'AZ', 52: 'BA', 701: 'ZZ', 702: 'AAA'
        }
        for idx, exp in cases.items():
            self.assertEqual(_idx_to_col(idx), exp)

    def test_get_local_stable_keys_success(self):
        # Provide a row containing date, amount, description, and id
        row = {'date_col': '2020-01-01', 'amt_col': 10.0, 'desc_col': 'note', 'id': 42}
        # Pre-seed parsed mapping
        self.manager._parsed_mapping = {
            'date': ['date_col'],
            'amount': ['amt_col'],
            'description': ['desc_col'],
        }
        keys = self.manager._get_local_stable_keys(row)
        self.assertEqual(keys['date'], ('2020-01-01',))
        self.assertEqual(keys['amount'], (10.0,))
        self.assertEqual(keys['description'], ('note',))
        self.assertEqual(keys['id'], (42,))

    def test_get_local_stable_keys_missing(self):
        # Missing date mapping should raise ValueError
        row = {'amt_col': 5.0, 'desc_col': 'x'}
        self.manager._parsed_mapping = {
            'date': ['date_col'],
            'amount': ['amt_col'],
            'description': ['desc_col'],
        }
        with self.assertRaises(ValueError) as cm:
            self.manager._get_local_stable_keys(row)
        self.assertIn('Mapping for stable key "date" references no valid column', str(cm.exception))

    def test_get_original_value(self):
        # If mapping spec yields a known column, return its value
        row = {'foo': 'orig_foo', 'bar': 'orig_bar'}
        # foo maps to itself via parse_mapping_spec stub
        val = self.manager._get_original_value(row, 'foo')
        self.assertEqual(val, 'orig_foo')
        # Unknown column returns row.get(column) -> None
        val2 = self.manager._get_original_value(row, 'baz')
        self.assertIsNone(val2)

    def test_queue_edit_and_squash_and_clear(self):
        # Stub DatabaseAPI.get_row, _get_local_stable_keys, _get_original_value
        dummy_row = {'col': 'orig'}
        with patch.object(sync_mod.DatabaseAPI, 'get_row', return_value=dummy_row), \
                patch.object(self.manager, '_get_local_stable_keys', return_value={'id': (1,)}), \
                patch.object(self.manager, '_get_original_value', return_value='orig'):
            # Queue first edit
            self.manager.queue_edit(1, 'col', 'new')
            ops = self.manager.get_queued_ops()
            self.assertEqual(len(ops), 1)
            op = ops[0]
            self.assertEqual(op.orig_value, 'orig')
            self.assertEqual(op.new_value, 'new')
            # Queue same edit again should squash and update new_value
            self.manager.queue_edit(1, 'col', 'new2')
            ops2 = self.manager.get_queued_ops()
            self.assertEqual(len(ops2), 1)
            self.assertEqual(ops2[0].new_value, 'new2')
            # Clear queue empties it
            self.manager.clear_queue()
            self.assertEqual(self.manager.get_queued_ops(), [])

    def test_queue_edit_no_local_row(self):
        # get_row returns None should raise ValueError
        with patch.object(sync_mod.DatabaseAPI, 'get_row', return_value=None):
            with self.assertRaises(ValueError):
                self.manager.queue_edit(999, 'col', 'val')

    def test_determine_stable_fields_with_id_header(self):
        headers = ['X', 'Num', 'Y']
        # 'Num' should be recognized as id alias
        fields = self.manager._determine_stable_fields(headers)
        self.assertEqual(fields, ['id'])

    def test_determine_stable_fields_without_id(self):
        # Prepare queue with a sample operation having stable_keys
        op = EditOperation(1, 'col', None, None, {'date': ('d',), 'amount': (2.0,), 'description': ('t',)})
        self.manager._queue = [op]
        fields = self.manager._determine_stable_fields(['A', 'B'])
        # Order should follow keys except 'id'
        self.assertEqual(fields, ['date', 'amount', 'description'])

    def test_build_stable_headers_map_success_and_failure(self):
        # Test id-only mapping
        headers = ['id', 'foo']
        hdr_map = self.manager._build_stable_headers_map(headers, ['id'])
        self.assertEqual(hdr_map, {'id': ['id']})
        # Test logical fields mapping
        self.manager._parsed_mapping = {'date': ['D1', 'D2'], 'amount': ['A']}  # D2 absent in headers
        hdr_map2 = self.manager._build_stable_headers_map(['D1', 'A', 'X'], ['date', 'amount'])
        self.assertEqual(hdr_map2, {'date': ['D1'], 'amount': ['A']})
        # Missing mapping should raise
        self.manager._parsed_mapping = {'date': ['Z']}
        with self.assertRaises(ValueError):
            self.manager._build_stable_headers_map(['D1'], ['date'])

    def test_fetch_stable_data_type_conversions(self):
        # Create a fake service returning mixed-type values
        svc = MagicMock()
        # Prepare three rows for each logical field
        vr_list = [
            [['44197'], ['bad'], []],  # date
            [['5.5'], ['7'], []],  # amount
            [['1.0'], ['x'], []],  # id
            [[' foo '], ['bar'], []],  # desc
        ]
        batch_get = MagicMock()
        batch_get.execute.return_value = {'valueRanges': [{'values': v} for v in vr_list]}
        svc.spreadsheets.return_value.values.return_value.batchGet.return_value = batch_get
        stable_map = {'date': ['D'], 'amount': ['A'], 'id': ['I'], 'desc': ['C']}
        hdr_idx = {'D': 0, 'A': 1, 'I': 2, 'C': 3}
        row_count = 4
        data_rows = 3
        result = self.manager._fetch_stable_data(svc, stable_map, hdr_idx, row_count, data_rows)
        # Date conversion via google_serial_date_to_iso
        exp_date = sync_mod.google_serial_date_to_iso(44197.0)
        self.assertEqual(result[('date', 'D')][0], exp_date)
        # Non-numeric date remains raw string on error
        self.assertEqual(result[('date', 'D')][1], 'bad')
        self.assertIsNone(result[('date', 'D')][2])
        # Amount conversion
        self.assertEqual(result[('amount', 'A')], [5.5, 7.0, None])
        # Id conversion
        self.assertEqual(result[('id', 'I')], [1, 'x', None])
        # Description trimming and empty fallback
        self.assertEqual(result[('desc', 'C')], ['foo', 'bar', ''])

    def test_assemble_and_index_and_match_operations(self):
        # Simulate two remote rows
        remote_rows = [
            {'amount': (10.0,), 'description': ('aa',)},
            {'amount': (20.0,), 'description': ('bb',)},
        ]
        stable_fields = ['amount', 'description']
        idx_map = self.manager._build_remote_index_map(remote_rows, stable_fields)
        # Check index mapping
        self.assertIn(((10.0,), ('aa',)), idx_map)
        self.assertEqual(idx_map[((10.0,), ('aa',))], [0])
        # Match a unique operation
        op = EditOperation(1, 'col', None, None, {'amount': (10.0,), 'description': ('aa',)})
        results = {}
        updates = self.manager._match_operations({((10.0,), ('aa',)): [0]}, stable_fields, results)
        # Should schedule update at row 2
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1], 2)
        self.assertTrue(results[(1, 'col')][0])
        # Ambiguous with disambiguation
        amb_map = {('key',): [0, 1]}
        op2 = EditOperation(2, 'c', None, None, {'amount': ('key',), 'description': ()})
        res2 = {}
        ups2 = self.manager._match_operations(amb_map, ['amount'], res2)
        # local_id=2 -> expected index 1 -> choose row 3
        self.assertEqual(ups2[0][1], 3)
        self.assertEqual(res2[(2, 'c')][1], 'Disambiguated by cache row order')
        # Ambiguous with no match
        res3 = {}
        op3 = EditOperation(3, 'c', None, None, {'amount': ('key',)})
        ups3 = self.manager._match_operations(amb_map, ['amount'], res3)
        # No update scheduled and flag as failure
        self.assertEqual(len(ups3), 0)
        self.assertFalse(res3[(3, 'c')][0])
        self.assertIn('Ambiguous match', res3[(3, 'c')][1])

    def test_build_update_payload(self):
        # Prepare a dummy operation
        op = EditOperation(1, 'colX', None, 99, {})
        # Seed parsed mapping and header_to_idx
        self.manager._parsed_mapping = {'colX': ['colX']}
        hdr_idx = {'colX': 4}
        # Build payload
        payload = self.manager._build_update_payload([(op, 5)], hdr_idx)
        self.assertEqual(payload['valueInputOption'], 'USER_ENTERED')
        # Range should reference row 5 and column 'E'
        self.assertEqual(payload['data'][0]['range'], f"{self.manager.worksheet}!E5")
        self.assertEqual(payload['data'][0]['values'], [[99]])
        # Missing header mapping
        self.manager._parsed_mapping = {'colX': ['other']}
        with self.assertRaises(ValueError):
            self.manager._build_update_payload([(op, 1)], hdr_idx)

    def test_commit_queue_empty_and_no_data(self):
        # Empty queue returns empty dict
        self.manager._queue = []
        self.assertEqual(self.manager.commit_queue(), {})
        # No data rows scenario
        # Seed two ops
        ops = [EditOperation(1, 'c', None, None, {}), EditOperation(2, 'c2', None, None, {})]
        self.manager._queue = ops.copy()
        # Stub sheet access and size
        with patch('ExpenseTracker.core.sync._verify_sheet_access', return_value=MagicMock()), \
                patch('ExpenseTracker.core.sync._query_sheet_size', return_value=(1, 5)):
            res = self.manager.commit_queue()
            # Both ops should have failure due to no data rows
            for op in ops:
                self.assertFalse(res[(op.local_id, op.column)][0])
                self.assertIn('no data rows'.lower(), res[(op.local_id, op.column)][1].lower())


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
