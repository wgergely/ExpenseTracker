"""Sync manager for queued local edits and safe batch-push to Google Sheets.

Implements optimistic-concurrency: edits are buffered locally, and on commit we
re-fetch the sheet data for stable key fields (date, amount, description), match
rows exactly, and if all still match, send a single batchUpdate. Ambiguities or
mismatches abort.

Stable key fields:
- date: mapped to date-like columns
- amount: mapped to numeric columns
- description: mapped to text columns

An 'id' alias (id, #, number, num) is also recognized as a primary stable key
if present.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

from PySide6 import QtCore
from googleapiclient.errors import HttpError

from .database import DatabaseAPI, google_serial_date_to_iso
from .service import (
    _verify_sheet_access,
    _query_sheet_size,
    start_asynchronous,
    TOTAL_TIMEOUT,
    _verify_mapping,
)
from ..settings import lib
from ..settings.lib import parse_mapping_spec


@dataclass
class EditOperation:
    """Represents one pending edit operation."""
    local_id: int
    column: str
    orig_value: Any
    new_value: Any
    stable_keys: Dict[str, Tuple[Any, ...]]


def _idx_to_col(idx: int) -> str:
    """Convert zero-based column index to spreadsheet letter(s)."""
    letters = ''
    while idx >= 0:
        letters = chr((idx % 26) + ord('A')) + letters
        idx = idx // 26 - 1
    return letters


class SyncManager(QtCore.QObject):
    """Buffer edits to transactions and commit them safely to the remote sheet."""
    commitFinished = QtCore.Signal(dict)
    dataUpdated = QtCore.Signal(list)
    queueChanged = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._queue: List[EditOperation] = []
        self._parsed_mapping: Dict[str, List[str]] = {}
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect external signals to queue-clearing slots.

        Returns:
            None
        """
        from ..ui.actions import signals

        signals.presetAboutToBeActivated.connect(self.clear_queue)
        signals.dataAboutToBeFetched.connect(self.clear_queue)

    @property
    def sheet_id(self) -> str:
        """Spreadsheet ID from settings."""
        config = lib.settings.get_section('spreadsheet')
        return config.get('id', '')

    @property
    def worksheet(self) -> str:
        """Worksheet name from settings."""
        config = lib.settings.get_section('spreadsheet')
        return config.get('worksheet', '')

    def queue_edit(self, local_id: int, column: str, new_value: Any) -> None:
        """Add an edit to the queue, recording original and stable key values.

        Args:
            local_id: Primary key of the local row.
            column: Logical column name to edit.
            new_value: The value to set.

        Raises:
            ValueError: If the row does not exist or mapping is invalid.

        Returns:
            None
        """
        logging.debug(f'Queueing edit: local_id={local_id}, column={column}, new_value={new_value}')
        row = DatabaseAPI.get_row(local_id)
        if row is None:
            raise ValueError(f'No local row with id {local_id}')

        stable_keys = self._get_local_stable_keys(row)
        orig_value = self._get_original_value(row, column)

        for op in self._queue:
            if op.local_id == local_id and op.column == column:
                op.new_value = new_value
                self.queueChanged.emit(len(self._queue))
                return

        self._queue.append(
            EditOperation(local_id, column, orig_value, new_value, stable_keys)
        )
        self.queueChanged.emit(len(self._queue))

    def get_queued_ops(self) -> List[EditOperation]:
        """Return the list of pending edits.

        Returns:
            List of EditOperation representing pending edits.
        """
        return list(self._queue)

    def clear_queue(self) -> None:
        """Discard all pending edits.

        Returns:
            None
        """
        self._queue.clear()
        self.queueChanged.emit(0)

    def commit_queue(self) -> Dict[Tuple[int, str], Tuple[bool, str]]:
        """Perform optimistic-lock commit: refetch, match, and batchUpdate.

        Returns:
            Mapping from (local_id, column) to (success, message).
        """
        results: Dict[Tuple[int, str], Tuple[bool, str]] = {}
        if not self._queue:
            return results

        logging.debug(f'Starting commit of {len(self._queue)} queued edit(s)')
        service = _verify_sheet_access()
        row_count, col_count = _query_sheet_size(
            service, self.sheet_id, self.worksheet
        )
        data_rows = max(row_count - 1, 0)
        if data_rows == 0:
            for op in self._queue:
                results[(op.local_id, op.column)] = (
                    False,
                    'Remote sheet has no data rows',
                )
            return results

        headers = self._fetch_headers(service, col_count)
        _verify_mapping(remote_headers=headers)
        header_to_idx = {h: i for i, h in enumerate(headers)}

        stable_fields = self._determine_stable_fields(headers)
        stable_map = self._build_stable_headers_map(headers, stable_fields)

        col_vals_map = self._fetch_stable_data(
            service, stable_map, header_to_idx, row_count, data_rows
        )
        remote_rows = self._assemble_remote_rows(
            col_vals_map, stable_fields, data_rows
        )
        remote_index_map = self._build_remote_index_map(
            remote_rows, stable_fields
        )
        to_update = self._match_operations(
            remote_index_map, stable_fields, results
        )

        if not to_update:
            failed = len([ok for ok, _ in results.values() if not ok])
            logging.info(
                f'No matching edits to apply; {failed} edit(s) failed to match criteria'
            )
            self.clear_queue()
            return results

        payload = self._build_update_payload(to_update, header_to_idx)
        try:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheet_id, body=payload
            ).execute()
            logging.info(
                f'Successfully pushed {len(to_update)} edit(s) to remote sheet'
            )
        except HttpError as ex:
            status = getattr(ex.resp, 'status', None)
            logging.error(
                f'Batch update HTTPError: status={status} detail={ex.error_details}'
            )
            for op, _ in to_update:
                results[(op.local_id, op.column)] = (
                    False,
                    f'HTTPError status={status}',
                )
            self.clear_queue()
            return results
        except Exception:
            logging.exception('Batch update failed for queued edits')
            for op, _ in to_update:
                results[(op.local_id, op.column)] = (
                    False,
                    'Batch update failed',
                )
            self.clear_queue()
            return results

        self._apply_local_updates(to_update, header_to_idx)
        self.dataUpdated.emit([op for op, _ in to_update])
        self.clear_queue()
        return results

    @QtCore.Slot()
    def commit_queue_async(self) -> None:
        """Run commit_queue in a QThread and emit commitFinished when done.

        Returns:
            None
        """
        logging.debug('Starting asynchronous commit_queue')
        result = start_asynchronous(
            self.commit_queue,
            total_timeout=TOTAL_TIMEOUT,
            status_text='Syncing edits.',
        )
        logging.debug(
            f'Asynchronous commit_queue completed with results: {result}'
        )
        self.commitFinished.emit(result)

    def _get_parsed_mapping(self, key: str) -> List[str]:
        """Get and cache parsed mapping spec for a logical key.

        Args:
            key: Logical field name to retrieve mapping for.

        Returns:
            List of column names parsed from the mapping spec.
        """
        if key not in self._parsed_mapping:
            raw = lib.settings.get_section('mapping').get(key, '')
            self._parsed_mapping[key] = parse_mapping_spec(raw)
        return self._parsed_mapping[key]

    def _get_local_stable_keys(self, row: Dict[str, Any]) -> Dict[str, Tuple[Any, ...]]:
        """Extract stable key tuples from a local row.

        Args:
            row: Dictionary mapping column names to values from local DB.

        Raises:
            ValueError: If a required stable key mapping has no valid columns.

        Returns:
            Mapping of logical stable fields to tuples of their values.
        """
        keys: Dict[str, Tuple[Any, ...]] = {}
        for logical in ('date', 'amount', 'description'):
            candidates = self._get_parsed_mapping(logical)
            present = [c for c in candidates if c in row]
            if not present:
                raise ValueError(
                    f'Mapping for stable key "{logical}" references no valid column'
                )
            keys[logical] = tuple(row[c] for c in present)
        id_aliases = {'id', '#', 'number', 'num'}
        id_key = next(
            (k for k in row if k.strip().lower() in id_aliases),
            None,
        )
        if id_key:
            keys['id'] = (row[id_key],)
        return keys

    def _get_original_value(self, row: Dict[str, Any], column: str) -> Any:
        """Resolve the original cell value for a logical column.

        Args:
            row: Dictionary mapping column names to values from local DB.
            column: Logical field name being edited.

        Returns:
            The original value before editing.
        """
        mapping_conf = lib.settings.get_section('mapping')
        raw_spec = mapping_conf.get(column, column)
        candidates = parse_mapping_spec(raw_spec)
        found = next((c for c in candidates if c in row), None)
        return row.get(found) if found else row.get(column)

    def _fetch_headers(self, service: Any, col_count: int) -> List[str]:
        """Fetch the header row from the remote sheet.

        Args:
            service: Authorized Sheets API service instance.
            col_count: Total columns in the sheet.

        Returns:
            List of header strings.
        """
        last_col = _idx_to_col(col_count - 1)
        hdr_range = f'{self.worksheet}!A1:{last_col}1'
        batch = service.spreadsheets().values().batchGet(
            spreadsheetId=self.sheet_id,
            ranges=[hdr_range],
            valueRenderOption='UNFORMATTED_VALUE',
            fields='valueRanges(values)',
        ).execute()
        vr = batch.get('valueRanges', [])
        if vr and vr[0].get('values'):
            return [str(cell) for cell in vr[0]['values'][0]]
        return []

    def _determine_stable_fields(self, headers: List[str]) -> List[str]:
        """Determine logical stable fields based on remote headers.

        Args:
            headers: Remote sheet headers.

        Returns:
            List of logical stable field names.
        """
        id_aliases = {'id', '#', 'number', 'num'}
        id_header = next(
            (h for h in headers if h.strip().lower() in id_aliases),
            None,
        )
        if id_header:
            return ['id']
        return [k for k in self._queue[0].stable_keys if k != 'id']

    def _build_stable_headers_map(
            self,
            headers: List[str],
            stable_fields: List[str],
    ) -> Dict[str, List[str]]:
        """Map logical stable fields to remote header names.

        Args:
            headers: Remote sheet headers.
            stable_fields: Logical stable field names.

        Raises:
            ValueError: If stable field has no valid remote headers.

        Returns:
            Mapping from logical field to list of matching headers.
        """
        hdr_map: Dict[str, List[str]] = {}
        if stable_fields == ['id']:
            id_aliases = {'id', '#', 'number', 'num'}
            id_header = next(
                (h for h in headers if h.strip().lower() in id_aliases),
                None,
            )
            hdr_map['id'] = [id_header] if id_header else []
        else:
            for logical in stable_fields:
                candidates = self._get_parsed_mapping(logical)
                present = [c for c in candidates if c in headers]
                if not present:
                    raise ValueError(
                        f'Mapping for stable key "{logical}" references no valid remote header'
                    )
                hdr_map[logical] = present
        return hdr_map

    def _fetch_stable_data(
            self,
            service: Any,
            stable_map: Dict[str, List[str]],
            header_to_idx: Dict[str, int],
            row_count: int,
            data_rows: int,
    ) -> Dict[Tuple[str, str], List[Any]]:
        """Fetch and normalize stable key columns from remote sheet.

        Args:
            service: Authorized Sheets API service instance.
            stable_map: Logical-to-remote header mapping.
            header_to_idx: Header name to column index mapping.
            row_count: Total rows in the sheet.
            data_rows: Number of data rows (excluding header).

        Returns:
            Mapping from (logical, header) to normalized values list.
        """
        ranges: List[str] = []
        for logical, hdrs in stable_map.items():
            for hdr in hdrs:
                idx = header_to_idx[hdr]
                col = _idx_to_col(idx)
                ranges.append(f'{self.worksheet}!{col}2:{col}{row_count}')
        batch = service.spreadsheets().values().batchGet(
            spreadsheetId=self.sheet_id,
            ranges=ranges,
            valueRenderOption='UNFORMATTED_VALUE',
            fields='valueRanges(values)',
        ).execute()
        vr_list = batch.get('valueRanges', [])
        col_vals: Dict[Tuple[str, str], List[Any]] = {}
        i = 0
        for logical, hdrs in stable_map.items():
            for hdr in hdrs:
                vr = vr_list[i] if i < len(vr_list) else {}
                i += 1
                raw = vr.get('values', [])
                flat = [r[0] if r else None for r in raw]
                flat += [None] * (data_rows - len(flat))
                normed: List[Any] = []
                for v in flat:
                    if logical == 'date':
                        try:
                            nv = google_serial_date_to_iso(float(v))
                        except Exception:
                            nv = v
                    elif logical == 'amount':
                        try:
                            nv = round(float(v), 2)
                        except Exception:
                            nv = v
                    elif logical == 'id':
                        try:
                            nv = int(float(v))
                        except Exception:
                            nv = v
                    else:
                        if v is None:
                            nv = ''
                        elif isinstance(v, str):
                            nv = v.strip()
                        else:
                            nv = v
                    normed.append(nv)
                col_vals[(logical, hdr)] = normed
        return col_vals

    def _assemble_remote_rows(
            self,
            col_vals: Dict[Tuple[str, str], List[Any]],
            stable_fields: List[str],
            data_rows: int,
    ) -> List[Dict[str, Any]]:
        """Build list of remote rows keyed by logical stable fields.

        Args:
            col_vals: Mapping from (logical, header) to values.
            stable_fields: Logical stable field names.
            data_rows: Number of data rows.

        Returns:
            List of row dicts mapping field to tuple of its values.
        """
        remote: List[Dict[str, Any]] = []
        for i in range(data_rows):
            entry: Dict[str, Any] = {}
            for logical in stable_fields:
                values = tuple(
                    col_vals[(logical, hdr)][i] for hdr in col_vals if hdr[0] == logical
                )
                entry[logical] = values
            remote.append(entry)
        return remote

    def _build_remote_index_map(
            self,
            remote_rows: List[Dict[str, Any]],
            stable_fields: List[str],
    ) -> Dict[Tuple[Any, ...], List[int]]:
        """Create index map from stable-key tuples to row indices.

        Args:
            remote_rows: List of remote row dict mappings.
            stable_fields: Logical stable field names.

        Returns:
            Mapping from key tuple to list of row indices.
        """
        index_map: Dict[Tuple[Any, ...], List[int]] = {}
        for idx, row in enumerate(remote_rows):
            key = tuple(row.get(field) for field in stable_fields)
            if all(
                    (v is None) or (isinstance(v, tuple) and all(elem is None for elem in v))
                    for v in key
            ):
                continue
            index_map.setdefault(key, []).append(idx)
        return index_map

    def _match_operations(
            self,
            remote_index_map: Dict[Tuple[Any, ...], List[int]],
            stable_fields: List[str],
            results: Dict[Tuple[int, str], Tuple[bool, str]],
    ) -> List[Tuple[EditOperation, int]]:
        """Match queued edits to remote rows and prepare update list.

        Args:
            remote_index_map: Mapping from key to row indices.
            stable_fields: Logical stable field names.
            results: Output mapping to record success/failure.

        Returns:
            List of tuples (EditOperation, sheet row number).
        """
        to_update: List[Tuple[EditOperation, int]] = []
        for op in self._queue:
            key = tuple(op.stable_keys.get(f) for f in stable_fields)
            matches = remote_index_map.get(key, [])
            k = (op.local_id, op.column)
            if len(matches) == 1:
                row_idx = matches[0] + 2
                to_update.append((op, row_idx))
                results[k] = (True, '')
            elif len(matches) > 1:
                expected = op.local_id - 1
                if expected in matches:
                    row_idx = expected + 2
                    to_update.append((op, row_idx))
                    results[k] = (True, 'Disambiguated by cache row order')
                else:
                    results[k] = (False, 'Ambiguous match; multiple rows match')
            else:
                results[k] = (False, 'No matching row; remote changed')
        return to_update

    def _build_update_payload(
            self,
            to_update: List[Tuple[EditOperation, int]],
            header_to_idx: Dict[str, int],
    ) -> Dict[str, Any]:
        """Construct the request body for batchUpdate.

        Args:
            to_update: List of (EditOperation, sheet row) tuples.
            header_to_idx: Header name to column index mapping.

        Raises:
            ValueError: If mapping for a column has no valid header.

        Returns:
            Request body dict for batchUpdate.
        """
        data: List[Dict[str, Any]] = []
        for op, sheet_row in to_update:
            candidates = self._get_parsed_mapping(op.column)
            found = next((c for c in candidates if c in header_to_idx), None)
            if not found:
                raise ValueError(
                    f'Mapping for "{op.column}" references no valid remote header'
                )
            idx_col = header_to_idx[found]
            col_letter = _idx_to_col(idx_col)
            data.append({
                'range': f'{self.worksheet}!{col_letter}{sheet_row}',
                'values': [[op.new_value]],
            })
        return {'valueInputOption': 'USER_ENTERED', 'data': data}

    def _apply_local_updates(
            self,
            to_update: List[Tuple[EditOperation, int]],
            header_to_idx: Dict[str, int],
    ) -> None:
        """Update local cache database for successful edits.

        Args:
            to_update: List of (EditOperation, sheet row) tuples.
            header_to_idx: Header name to column index mapping.

        Returns:
            None
        """
        for op, _ in to_update:
            try:
                candidates = self._get_parsed_mapping(op.column)
                db_col = next((c for c in candidates if c in header_to_idx), None) or op.column
                DatabaseAPI.update_cell(op.local_id, db_col, op.new_value)
            except Exception:
                logging.exception(f'Failed to update local cache for id {op.local_id}')


sync_manager = SyncManager()
