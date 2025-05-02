"""
Sync manager for queued local edits and safe batch‐push to Google Sheets.

Implements optimistic‐concurrency: edits are buffered locally, and on commit we re‐fetch
the sheet data for stable key fields (date, amount, description), match rows exactly,
and if all still match, send a single batchUpdate.  Ambiguities or mismatches abort.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

from PySide6 import QtCore
from googleapiclient.errors import HttpError

from .database import DatabaseAPI, google_serial_date_to_iso
from .service import _verify_sheet_access, _query_sheet_size, start_asynchronous, TOTAL_TIMEOUT, \
    _verify_mapping
from ..settings import lib
from ..settings.lib import parse_mapping_spec


@dataclass
class EditOperation:
    """
    Represents one pending edit operation.
    """
    local_id: int
    column: str
    orig_value: Any
    new_value: Any
    stable_keys: Dict[str, Any]


def _idx_to_col(idx: int) -> str:
    """Convert zero-based column index to spreadsheet letter(s)."""
    letters = ''
    while idx >= 0:
        letters = chr((idx % 26) + ord('A')) + letters
        idx = idx // 26 - 1
    return letters


class SyncManager(QtCore.QObject):
    """
    Buffer edits to transactions and commit them safely to the remote sheet.

    Emits:
      dataUpdated(List[EditOperation]): after the local cache has been updated.
      commitFinished(dict): with per-row results.

    """
    commitFinished = QtCore.Signal(object)
    dataUpdated = QtCore.Signal(list)
    queueChanged = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._queue: List[EditOperation] = []

        self._connect_signals()

    def _connect_signals(self) -> None:
        """
        Connect signals to slots.
        """
        from ..ui.actions import signals
        signals.presetAboutToBeActivated.connect(self.clear_queue)
        signals.dataAboutToBeFetched.connect(self.clear_queue)

    @property
    def sheet_id(self) -> str:
        config = lib.settings.get_section('spreadsheet')
        return config.get('id', '')

    @property
    def worksheet(self) -> str:
        config = lib.settings.get_section('spreadsheet')
        return config.get('worksheet', '')

    def queue_edit(self, local_id: int, column: str, new_value: Any) -> None:
        """
        Add an edit to the queue, recording the original and stable key values.
        """
        logging.debug(f'Queueing edit: local_id={local_id}, column={column}, new_value={new_value}')
        # fetch the local database row
        row = DatabaseAPI.get_row(local_id)
        if not row:
            raise ValueError(f'No local row with id {local_id}')
        # resolve stable key values using mapping; collect all mapped columns per logical key
        mapping_conf = lib.settings.get_section('mapping')
        stable_fields = ['date', 'amount', 'description']
        stable: Dict[str, Tuple[Any, ...]] = {}
        for logical in stable_fields:
            raw_spec = mapping_conf.get(logical)
            candidates = parse_mapping_spec(raw_spec)
            present = [c for c in candidates if c in row]
            if not present:
                raise ValueError(f'Mapping for stable key "{logical}" references no valid column: {raw_spec}')
            # store tuple of values for all mapped source columns
            stable[logical] = tuple(row.get(c) for c in present)
        # include any sheet ID-like column as a primary stable key if available
        id_aliases = {'id', '#', 'number', 'num'}
        id_key = next((k for k in row.keys() if k.strip().lower() in id_aliases), None)
        if id_key is not None:
            stable['id'] = (row.get(id_key),)
        # determine the original value for the edited column
        # column is a logical name; map to actual DB column via mapping
        # determine the original value for the edited column using its mapping (first candidate)
        raw_spec_col = mapping_conf.get(column, column)
        candidates_col = parse_mapping_spec(raw_spec_col)
        found_col = next((c for c in candidates_col if c in row), None)
        orig = row.get(found_col) if found_col is not None else row.get(column)
        # If an edit for this cell is already queued, squash it
        for op in self._queue:
            if op.local_id == local_id and op.column == column:
                op.new_value = new_value
                # emit queue size unchanged
                self.queueChanged.emit(len(self._queue))
                return

        self._queue.append(EditOperation(local_id, column, orig, new_value, stable))
        self.queueChanged.emit(len(self._queue))

    def get_queued_ops(self) -> List[EditOperation]:
        """Return the list of pending edits."""
        return list(self._queue)

    def clear_queue(self) -> None:
        """Discard all pending edits."""
        self._queue.clear()
        self.queueChanged.emit(0)

    def commit_queue(self) -> Dict[Tuple[int, str], Tuple[bool, str]]:
        """
        Perform optimistic‐lock commit: refetch remote stable fields, match, and batchUpdate.
        Returns a mapping (local_id, column) → (success, message).
        """
        # track per-operation success/failure keyed by (local_id, column)
        results: Dict[Tuple[int, str], Tuple[bool, str]] = {}
        if not self._queue:
            return results

        logging.debug(f'Starting commit of {len(self._queue)} queued edit(s)')
        # verify access and get service client
        service = _verify_sheet_access()

        # determine sheet size (rows, cols)
        row_count, col_count = _query_sheet_size(service, self.sheet_id, self.worksheet)
        logging.debug(f'Sheet dimensions: rows={row_count}, cols={col_count}')
        data_rows = max(row_count - 1, 0)
        if data_rows == 0:
            for op in self._queue:
                results[(op.local_id, op.column)] = (False, 'Remote sheet has no data rows')
            return results

        # fetch header row in one request
        last_col = _idx_to_col(col_count - 1)
        hdr_range = f'{self.worksheet}!A1:{last_col}1'
        logging.debug(f'Fetching header row with range: {hdr_range}')
        hdr_batch = service.spreadsheets().values().batchGet(
            spreadsheetId=self.sheet_id,
            ranges=[hdr_range],
            valueRenderOption='UNFORMATTED_VALUE',
            fields='valueRanges(values)',
        ).execute()
        # parse headers
        ranges_out = hdr_batch.get('valueRanges', [])
        if ranges_out and ranges_out[0].get('values'):
            headers = [str(cell) for cell in ranges_out[0]['values'][0]]
        else:
            headers = []
        logging.debug(f'Remote sheet headers: {headers}')

        # verify header mapping configuration
        mapping = lib.settings.get_section('mapping')
        logging.debug(f'Using header mapping: {mapping}')
        _verify_mapping(remote_headers=headers)
        logging.debug('Header mapping verified successfully')
        header_to_idx = {h: i for i, h in enumerate(headers)}

        # determine stable fields: prefer a remote 'ID'-like column if present
        headers = list(header_to_idx.keys())
        id_aliases = {'id', '#', 'number', 'num'}
        id_header = next((h for h in headers if h.strip().lower() in id_aliases), None)
        stable_headers_map: Dict[str, List[str]]
        if id_header:
            stable_fields = ['id']
            stable_headers_map = {'id': [id_header]}
            logging.debug(f'Using remote sheet column "{id_header}" as primary stable key')
        else:
            # fallback to date, amount, description
            stable_fields = [k for k in self._queue[0].stable_keys.keys() if k != 'id']
            stable_headers_map = {}
            for logical in stable_fields:
                raw_spec = mapping.get(logical)
                candidates = parse_mapping_spec(raw_spec)
                present = [c for c in candidates if c in header_to_idx]
                if not present:
                    raise ValueError(
                        f'Mapping for stable key "{logical}" references no valid remote header: {raw_spec}'
                    )
                stable_headers_map[logical] = present
        logging.debug(f'Stable headers map: {stable_headers_map}')

        # fetch all stable-key columns ranges
        ranges: List[str] = []
        for logical, hdrs in stable_headers_map.items():
            for hdr in hdrs:
                idx = header_to_idx[hdr]
                col = _idx_to_col(idx)
                ranges.append(f'{self.worksheet}!{col}2:{col}{row_count}')
        logging.debug(f'Fetching stable-key data ranges: {ranges}')
        batch = service.spreadsheets().values().batchGet(
            spreadsheetId=self.sheet_id,
            ranges=ranges,
            valueRenderOption='UNFORMATTED_VALUE',
            fields='valueRanges(values)',
        ).execute()

        # build (logical, header) → values list, normalized
        col_vals_map: Dict[Tuple[str, str], List[Any]] = {}
        vr_list = batch.get('valueRanges', [])
        idx_vr = 0
        for logical, hdrs in stable_headers_map.items():
            for hdr in hdrs:
                vr = vr_list[idx_vr] if idx_vr < len(vr_list) else {}
                idx_vr += 1
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
                            # round numeric values to 2 decimal places for robust matching
                            nv = round(float(v), 2)
                        except Exception:
                            nv = v
                    elif logical == 'id':
                        try:
                            nv = int(float(v))
                        except Exception:
                            nv = v
                    else:
                        # normalize text: strip whitespace and replace blanks with empty string
                        if v is None:
                            nv = ''
                        elif isinstance(v, str):
                            nv = v.strip()
                        else:
                            nv = v
                    normed.append(nv)
                col_vals_map[(logical, hdr)] = normed

        # assemble remote rows for matching stable keys
        remote: List[Dict[str, Any]] = []
        for i in range(data_rows):
            row_map: Dict[str, Any] = {}
            for logical in stable_fields:
                values = tuple(col_vals_map[(logical, hdr)][i] for hdr in stable_headers_map[logical])
                row_map[logical] = values
            remote.append(row_map)
        logging.debug(f'Assembled {len(remote)} remote rows for matching stable keys')

        # build a mapping from stable key tuples to remote row indices
        # (reuse stable_fields determined earlier)
        remote_index_map: Dict[Tuple[Any, ...], List[int]] = {}
        # build a mapping from stable key tuples to remote row indices, skipping blank rows
        for idx, row in enumerate(remote):
            key_tuple = tuple(row.get(field) for field in stable_fields)
            # skip rows where all stable key values are blank
            if all(
                    (v is None) or (isinstance(v, tuple) and all(elem is None for elem in v))
                    for v in key_tuple
            ):
                continue
            remote_index_map.setdefault(key_tuple, []).append(idx)
        logging.debug(f'Build remote index map (stable_fields={stable_fields}) of {len(remote_index_map)} entries')

        # match each edit operation and collect updates
        to_update: List[Tuple[EditOperation, int]] = []
        for op in self._queue:
            key_tuple = tuple(op.stable_keys.get(field) for field in stable_fields)
            matches = remote_index_map.get(key_tuple, [])
            logging.debug(f'Op {op.local_id} key {key_tuple} -> matches {matches}')
            key = (op.local_id, op.column)
            if len(matches) == 1:
                idx = matches[0]
                sheet_row = idx + 2
                to_update.append((op, sheet_row))
                results[key] = (True, '')
            elif len(matches) > 1:
                expected_idx = op.local_id - 1
                if expected_idx in matches:
                    sheet_row = expected_idx + 2
                    to_update.append((op, sheet_row))
                    results[key] = (True, 'Disambiguated by cache row order')
                    logging.warning(f'Ambiguous matches for op {op.local_id}, disambiguated to row {sheet_row}')
                else:
                    results[key] = (False, 'Ambiguous match; multiple rows match')
            else:
                results[key] = (False, 'No matching row; remote changed')

        # abort if no valid updates after matching
        if not to_update:
            failed_count = len([ok for ok, msg in results.values() if not ok])
            logging.info(f'No matching edits to apply; {failed_count} edit(s) failed to match criteria')
            self.clear_queue()
            return results

        # prepare batch update payload (single target column per operation)
        data: List[Dict[str, Any]] = []
        for op, sheet_row in to_update:
            # resolve target header for this logical column
            raw_spec = mapping.get(op.column)
            candidates = parse_mapping_spec(raw_spec)
            found = next((c for c in candidates if c in header_to_idx), None)
            if not found:
                raise ValueError(f'Mapping for "{op.column}" references no valid remote header: {raw_spec}')
            idx_col = header_to_idx[found]
            col_letter = _idx_to_col(idx_col)
            data.append({
                'range': f'{self.worksheet}!{col_letter}{sheet_row}',
                'values': [[op.new_value]],
            })
        body = {'valueInputOption': 'USER_ENTERED', 'data': data}
        try:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=body,
            ).execute()
            logging.info(f'Successfully pushed {len(to_update)} edit(s) to remote sheet')
        except HttpError as ex:
            # Log detailed HTTP error information
            status_code = getattr(ex, 'status_code', None)
            content = getattr(ex, 'content', None)
            logging.error(
                f'Batch update HTTPError: status={status_code}, content={content}'
            )
            for op, _ in to_update:
                key = (op.local_id, op.column)
                results[key] = (False, f'Batch update HTTPError: status={status_code}')
            self.clear_queue()
            return results
        except Exception:
            logging.exception('Batch update failed for queued edits')
            for op, _ in to_update:
                key = (op.local_id, op.column)
                results[key] = (False, 'Batch update failed')
            self.clear_queue()
            return results

        # update local cache database for successful edits, mapping logical to DB column
        for op, _ in to_update:
            try:
                # resolve the actual DB column via mapping spec and sheet headers
                raw_spec = mapping.get(op.column)
                candidates = parse_mapping_spec(raw_spec)
                # pick first candidate present in header_to_idx (and thus in DB)
                db_col = next((c for c in candidates if c in header_to_idx), None)
                if not db_col:
                    db_col = op.column
                DatabaseAPI.update_cell(op.local_id, db_col, op.new_value)
            except Exception:
                logging.exception(f'Failed to update local cache for id {op.local_id}')

        self.dataUpdated.emit([op for op, _ in to_update])
        self.clear_queue()
        return results

    @QtCore.Slot()
    def commit_queue_async(self) -> None:
        """Run commit_queue in a QThread and emit commitFinished when done."""
        logging.debug('Starting asynchronous commit_queue')
        result = start_asynchronous(
            self.commit_queue,
            total_timeout=TOTAL_TIMEOUT,
            status_text='Syncing edits.',
        )
        logging.debug(f'Asynchronous commit_queue completed with results: {result}')
        self.commitFinished.emit(result)


sync_manager = SyncManager()
