"""
Sync manager for queued local edits and safe batch‐push to Google Sheets.

Implements optimistic‐concurrency: edits are buffered locally, and on commit we re‐fetch
the sheet data for stable key fields (date, amount, description), match rows exactly,
and if all still match, send a single batchUpdate.  Ambiguities or mismatches abort.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from PySide6 import QtCore

from .database import DatabaseAPI, google_serial_date_to_iso
from .service import _verify_sheet_access, _fetch_headers, _query_sheet_size, start_asynchronous, TOTAL_TIMEOUT, \
    _verify_mapping
from ..settings import lib


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


class SyncManager(QtCore.QObject):  # noqa: WPS214
    """
    Buffer edits to transactions and commit them safely to the remote sheet.
    Emits:
      - dataUpdated(List[EditOperation]): after local cache has been updated
      - commitFinished(dict): with per-row results
    """
    commitFinished = QtCore.Signal(object)
    dataUpdated = QtCore.Signal(list)
    queueChanged = QtCore.Signal(int)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: List[EditOperation] = []

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
        row = DatabaseAPI.get_row(local_id)
        if not row:
            raise ValueError(f'No local row with id {local_id}')
        stable = {
            'date': row.get('date'),
            'amount': row.get('amount'),
            'description': row.get('description'),
        }
        orig = row.get(column)
        # If an edit for this cell is already queued, squash it (keep orig_value, update new_value)
        for op in self._queue:
            if op.local_id == local_id and op.column == column:
                op.new_value = new_value
                # emit queue size unchanged
                self.queueChanged.emit(len(self._queue))
                return
        # otherwise append a new operation
        self._queue.append(EditOperation(local_id, column, orig, new_value, stable))
        # notify UI of queue size change
        self.queueChanged.emit(len(self._queue))

    def get_queued_ops(self) -> List[EditOperation]:  # noqa: WPS210
        """Return the list of pending edits."""
        return list(self._queue)

    def clear_queue(self) -> None:
        """Discard all pending edits."""
        self._queue.clear()
        # notify UI the queue is now empty
        self.queueChanged.emit(0)

    def commit_queue(self) -> Dict[int, Tuple[bool, str]]:
        """
        Perform optimistic‐lock commit: refetch remote stable fields, match, and batchUpdate.
        Returns a mapping local_id → (success, message).
        """
        results: Dict[int, Tuple[bool, str]] = {}
        if not self._queue:
            return results

        logging.debug(f'Starting commit of {len(self._queue)} queued edit(s)')
        # verify access
        service = _verify_sheet_access()
        # fetch headers
        headers = _fetch_headers()
        logging.debug(f'Remote sheet headers: {headers}')
        # verify header mapping configuration
        mapping = lib.settings.get_section('mapping')
        logging.debug(f'Using header mapping: {mapping}')
        _verify_mapping(remote_headers=headers)
        logging.debug('Header mapping verified successfully')
        header_to_idx = {h: i for i, h in enumerate(headers)}

        # determine sheet size
        row_count, _ = _query_sheet_size(service, self.sheet_id, self.worksheet)
        data_rows = max(row_count - 1, 0)
        if data_rows == 0:
            for op in self._queue:
                results[op.local_id] = (False, 'Remote sheet has no data rows')
            return results

        # which logical columns to fetch
        needed = set()
        for op in self._queue:
            needed.update(op.stable_keys.keys())
            needed.add(op.column)

        ranges: List[str] = []
        for logical in needed:
            hdr = mapping.get(logical)
            idx = header_to_idx[hdr]
            col = _idx_to_col(idx)
            ranges.append(f'{self.worksheet}!{col}2:{col}{row_count}')

        batch = service.spreadsheets().values().batchGet(
            spreadsheetId=self.sheet_id,
            ranges=ranges,
            valueRenderOption='UNFORMATTED_VALUE',
            fields='valueRanges(values)',
        ).execute()

        # build column→values lists, padded to data_rows
        col_vals: Dict[str, List[Any]] = {}
        for logical, vr in zip(needed, batch.get('valueRanges', [])):
            raw = vr.get('values', [])
            flat = [r[0] if r else None for r in raw]
            # pad
            flat += [None] * (data_rows - len(flat))
            # normalize stable types
            normed: List[Any] = []
            for v in flat:
                if logical == 'date':
                    try:
                        nv = google_serial_date_to_iso(float(v))
                    except Exception:
                        nv = v
                elif logical == 'amount':
                    try:
                        nv = float(v)
                    except Exception:
                        nv = v
                else:
                    nv = v
                normed.append(nv)
            col_vals[logical] = normed

        # assemble remote rows by index
        remote: List[Dict[str, Any]] = []
        for i in range(data_rows):
            remote.append({logical: col_vals[logical][i] for logical in needed})

        # match each op
        to_update: List[Tuple[EditOperation, int]] = []  # op, sheet_row
        for op in self._queue:
            matches: List[int] = []
            for i, row in enumerate(remote):
                ok = True
                for key, val in op.stable_keys.items():
                    if row.get(key) != val:
                        ok = False
                        break
                if ok:
                    matches.append(i)
            if len(matches) == 1:
                sheet_row = matches[0] + 2
                to_update.append((op, sheet_row))
                results[op.local_id] = (True, '')
            elif not matches:
                results[op.local_id] = (False, 'No matching row; remote changed')
            else:
                results[op.local_id] = (False, 'Ambiguous match; multiple rows match')

        # abort on any failure
        if any(not ok for ok, _ in results.values()):
            return results

        # batchUpdate all
        data: List[Dict[str, Any]] = []
        for op, sheet_row in to_update:
            hdr = mapping.get(op.column)
            idx = header_to_idx[hdr]
            col = _idx_to_col(idx)
            data.append({
                'range': f'{self.worksheet}!{col}{sheet_row}',
                'values': [[op.new_value]],
            })
        body = {'valueInputOption': 'USER_ENTERED', 'data': data}
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=self.sheet_id,
            body=body,
        ).execute()

        # update local cache database
        for op, _ in to_update:
            try:
                DatabaseAPI.update_cell(op.local_id, op.column, op.new_value)
            except Exception:
                logging.exception(f'Failed to update local cache for id {op.local_id}')

        # notify listeners that local data has been updated
        self.dataUpdated.emit([op for op, _ in to_update])

        # clear the edit queue
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
        self.commitFinished.emit(result)


# singleton for app use
sync_manager = SyncManager()
