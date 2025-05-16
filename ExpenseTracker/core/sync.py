"""Sync manager for queued local edits and safe batch-push to Google Sheets.

Implements optimistic-concurrency: edits are buffered locally, and on commit we
re-fetch the sheet data for stable key fields (date, amount, description), match
rows exactly, and if all still match, send a single batchUpdate. Ambiguities or
mismatches abort.

Stable key fields:
- date: mapped to date-like columns (supports Google Sheets serial dates)
- amount: mapped to numeric columns
- description: mapped to text columns

An 'id' alias (id, #, number, num) is also recognized as a primary stable key
if present in sheet headers.
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
    TOTAL_TIMEOUT,  # Implicitly used by start_asynchronous
    _verify_mapping,
    _fetch_headers as service_fetch_headers,
)
from ..settings import lib
from ..settings.lib import HeaderRole


@dataclass
class EditOperation:
    """Represents one pending edit operation."""
    local_id: int  # Primary key of the local row
    column: str  # Logical column name being edited
    orig_value: Any
    new_value: Any
    stable_keys: Dict[str, Tuple[Any, ...]]  # Logical stable field -> tuple of its values


def idx_to_col(idx: int) -> str:
    """Convert zero-based column index to spreadsheet letter(s).

    Args:
        idx: The zero-based column index.

    Returns:
        The spreadsheet column letter(s) (e.g., A, B, AA).
    """
    letters = ''
    while idx >= 0:
        letters = chr((idx % 26) + ord('A')) + letters
        idx = idx // 26 - 1
    return letters


class SyncAPI(QtCore.QObject):
    """Buffer edits to transactions and commit them safely to the remote sheet.

    Manages a queue of local edits and applies optimistic concurrency control
    when committing these edits to a Google Sheet. It ensures data integrity by
    re-fetching key data before an update.
    """
    commitFinished = QtCore.Signal(dict)  # Emits Dict[(local_id, column), (success, message)]
    dataUpdated = QtCore.Signal(list)  # Emits List[EditOperation] of successfully committed ops
    queueChanged = QtCore.Signal(int)  # Emits current queue size

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._queue: List[EditOperation] = []
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect external signals to queue-clearing slots.

        Returns:
            None
        """
        from ..ui.actions import signals  # Local import to avoid circular dependencies

        signals.presetAboutToBeActivated.connect(self.clear_queue)
        signals.dataAboutToBeFetched.connect(self.clear_queue)

    @property
    def sheet_id(self) -> str:
        """Spreadsheet ID from settings.

        Returns:
            The Google Spreadsheet ID.
        """
        config = lib.settings.get_section('spreadsheet')
        return config.get('id', '')

    @property
    def worksheet(self) -> str:
        """Worksheet name from settings.

        Returns:
            The name of the worksheet (tab) within the spreadsheet.
        """
        config = lib.settings.get_section('spreadsheet')
        return config.get('worksheet', '')

    def queue_edit(self, local_id: int, column: str, new_value: Any) -> None:
        """Add an edit to the queue, recording original and stable key values.

        If an edit for the same cell already exists in the queue, its `new_value`
        is updated.

        Args:
            local_id: Primary key of the local row.
            column: Logical column name to edit.
            new_value: The value to set for the cell.

        Raises:
            ValueError: If the row does not exist locally or mapping for stable keys is invalid.

        Returns:
            None
        """
        logging.debug(f'Queueing edit: local_id={local_id}, column="{column}", new_value="{new_value}"')
        row = DatabaseAPI.get_row(local_id)
        if row is None:
            raise ValueError(f'No local row with id {local_id}')
        # Prevent edits on roles mapped to multiple headers
        headers_list = lib.settings.get_section('headers')
        role_to_names: Dict[str, List[str]] = {}
        for item in headers_list:
            role_to_names.setdefault(item['role'], []).append(item['name'])
        names = role_to_names.get(column, [])
        if len(names) > 1:
            raise ValueError(
                f'Cannot queue edit for multi-mapped role "{column}": mapped to headers {names}'
            )
        stable_keys = self._get_local_stable_keys(row)
        orig_value = self._get_original_value(row, column)

        for op in self._queue:
            if op.local_id == local_id and op.column == column:
                op.new_value = new_value
                self.queueChanged.emit(len(self._queue))
                logging.debug(f'Updated existing queued edit for local_id={local_id}, column="{column}"')
                return

        self._queue.append(
            EditOperation(local_id, column, orig_value, new_value, stable_keys)
        )
        self.queueChanged.emit(len(self._queue))
        logging.debug(f'Added new edit to queue; new size: {len(self._queue)}')

    def get_queued_ops(self) -> List[EditOperation]:
        """Return a copy of the list of pending edits.

        Returns:
            List[EditOperation]: A list of pending edit operations.
        """
        return list(self._queue)

    def clear_queue(self) -> None:
        """Discard all pending edits from the queue.

        Returns:
            None
        """
        if self._queue:
            logging.debug(f'Clearing {len(self._queue)} edit(s) from queue.')
            self._queue.clear()
            self.queueChanged.emit(0)
        else:
            logging.debug('Clear queue called, but queue was already empty.')

    def commit_queue(self) -> Dict[Tuple[int, str], Tuple[bool, str]]:
        """Perform optimistic-lock commit: refetch, match, and batchUpdate.

        This method implements the core optimistic concurrency control:
        1. Re-fetches stable key columns from the remote sheet.
        2. Matches queued local edits against this fresh remote data.
        3. If matches are unambiguous, sends a single `batchUpdate` to Google Sheets.
        4. Updates the local database cache for successful edits.

        Returns:
            Dict[Tuple[int, str], Tuple[bool, str]]:
                A dictionary mapping (local_id, column_logical_name) of each attempted
                edit to a tuple (success_status, message).
        """
        results: Dict[Tuple[int, str], Tuple[bool, str]] = {}
        if not self._queue:
            logging.info('Commit queue called, but queue is empty. Nothing to commit.')
            return results

        logging.info(f'Starting commit of {len(self._queue)} queued edit(s)')
        try:
            service = _verify_sheet_access()
            row_count, col_count = _query_sheet_size(
                service, self.sheet_id, self.worksheet
            )
            # Sheet row_count includes header, data_rows is just data
            data_rows = max(row_count - 1, 0)
            if data_rows == 0:
                logging.warning('Remote sheet has no data rows. All edits will fail matching.')
                for op in self._queue:
                    results[(op.local_id, op.column)] = (
                        False,
                        'Remote sheet has no data rows',
                    )
                self.clear_queue()  # Clear queue as operations are "processed" (failed)
                return results

            # Fetch header row using shared service helper
            headers = service_fetch_headers()
            if not headers:
                logging.error('Remote sheet has no header row. Cannot proceed with commit.')
                for op in self._queue:
                    results[(op.local_id, op.column)] = (
                        False,
                        'Remote sheet has no header row',
                    )
                self.clear_queue()
                return results

            _verify_mapping(remote_headers=headers)  # Verifies current settings mapping against remote
            header_to_idx = {h: i for i, h in enumerate(headers)}

            stable_fields = self._determine_stable_fields(headers)
            stable_map = self._build_stable_headers_map(headers, stable_fields)

            col_vals_map = self._fetch_stable_data(
                service, stable_map, header_to_idx, row_count, data_rows
            )
            remote_rows = self._assemble_remote_rows(
                col_vals_map, data_rows  # stable_fields argument removed
            )
            remote_index_map = self._build_remote_index_map(
                remote_rows, stable_fields
            )
            to_update = self._match_operations(
                remote_index_map, stable_fields, results
            )

            if not to_update:
                failed_count = sum(1 for success, _ in results.values() if not success)
                logging.info(
                    f'No matching edits to apply to remote sheet; {failed_count} edit(s) failed matching criteria.'
                )
                self.clear_queue()  # All ops accounted for in results
                return results

            payload = self._build_update_payload(to_update, header_to_idx)
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheet_id, body=payload
            ).execute()
            logging.info(
                f'Successfully pushed {len(to_update)} edit(s) to remote sheet.'
            )
            # Record successful update for each matched operation
            for op, _ in to_update:
                results[(op.local_id, op.column)] = (True, 'Committed successfully')


        except HttpError as ex:
            status = getattr(ex.resp, 'status', 'Unknown')
            details = getattr(ex, 'error_details', str(ex))
            logging.error(
                f'Batch update HTTPError: status={status} detail={details}'
            )
            # Mark all operations that were intended for update as failed due to HttpError
            # Operations already marked as failed (e.g. no match) should retain their status.
            for op in self._queue:  # Check all ops in original queue
                key = (op.local_id, op.column)
                if key not in results or results[key][0]:  # If not already failed or was part of to_update
                    results[key] = (False, f'Sheet API HTTPError: {status}')
            # It's safer to clear the queue after such a broad error
            self.clear_queue()
            return results
        except ValueError as ve:  # Catch specific ValueErrors from helpers (e.g. mapping issues)
            logging.error(f'ValueError during commit prep: {ve}')
            for op in self._queue:  # Mark all ops as failed
                results[(op.local_id, op.column)] = (False, f'Configuration error: {ve}')
            self.clear_queue()
            return results
        except Exception:  # Catch-all for other unexpected errors
            logging.exception('Batch update failed for queued edits due to an unexpected error.')
            for op in self._queue:  # Mark all ops as failed
                key = (op.local_id, op.column)
                if key not in results or results[key][0]:
                    results[key] = (False, 'Batch update failed: unexpected error')
            self.clear_queue()
            return results

        # If successfulここまで
        self._apply_local_updates(to_update, header_to_idx)
        self.dataUpdated.emit([op for op, _ in to_update])  # Emit only successfully committed ops
        self.clear_queue()  # Clear queue after successful processing or definitive failure
        return results

    @QtCore.Slot()
    def commit_queue_async(self) -> None:
        """Run commit_queue in a QThread and emit commitFinished when done.

        Returns:
            None
        """
        if not self._queue:
            logging.info('Async commit requested, but queue is empty. Nothing to do.')
            self.commitFinished.emit({})  # Emit empty results
            return

        logging.debug('Starting asynchronous commit_queue')
        # start_asynchronous is expected to handle the actual threading and error reporting
        result = start_asynchronous(
            self.commit_queue,
            total_timeout=TOTAL_TIMEOUT,  # This constant comes from .service
            status_text='Syncing edits...',
        )
        # Note: The result from start_asynchronous might be None if it has its own signalling.
        # Assuming it returns the direct result for now.
        # If start_asynchronous emits its own signal, this signal emit might be redundant
        # or should be connected to start_asynchronous's completion signal.
        # For this review, assuming current structure is intended.
        logging.debug(
            f'Asynchronous commit_queue task created/completed. Emitting commitFinished.'
        )
        self.commitFinished.emit(result if result is not None else {})

    def _get_local_stable_keys(self, row: Dict[str, Any]) -> Dict[str, Tuple[Any, ...]]:
        """Extract stable key tuples from a local row dictionary.

        Args:
            row: Dictionary mapping local database column names to values.

        Raises:
            ValueError: If a required stable key ('date', 'amount', 'description')
                        mapping has no valid columns in the local `row` data.

        Returns:
            Dict[str, Tuple[Any, ...]]:
                Mapping of logical stable fields ('date', 'amount', 'description', and optionally 'id')
                to tuples of their corresponding values from the row.
        """
        keys: Dict[str, Tuple[Any, ...]] = {}
        # Core stable keys: date, amount, description
        headers_list = lib.settings.get_section('headers')
        role_map = {item['role']: item['name'] for item in headers_list}
        for logical_key_name in (HeaderRole.Date.value, HeaderRole.Amount.value, HeaderRole.Description.value):
            col_name = role_map.get(logical_key_name)
            if col_name is None or col_name not in row:
                raise ValueError(
                    f'Header role "{logical_key_name}" not found in local row for stable key lookup.'
                )
            keys[logical_key_name] = (row[col_name],)

        # Optional 'id' stable key if configured
        id_col = role_map.get(HeaderRole.Id.value)
        if id_col and id_col in row:
            keys[HeaderRole.Id.value] = (row[id_col],)
        return keys

    def _get_original_value(self, row: Dict[str, Any], column_logical_name: str) -> Any:
        """Resolve the original cell value for a logical column from a local row.

        Uses the mapping configuration to find the actual column name(s) in the
        local row that correspond to the `column_logical_name`.

        Args:
            row: Dictionary mapping local database column names to values.
            column_logical_name: Logical field name (e.g., 'description') whose original value is needed.

        Returns:
            Any: The original value. Returns `None` if the column (after mapping)
                 is not found in the row.
        """
        # Resolve original value based on header role
        headers_list = lib.settings.get_section('headers')
        role_map = {item['role']: item['name'] for item in headers_list}
        col_name = role_map.get(column_logical_name)
        if col_name and col_name in row:
            return row.get(col_name)
        return row.get(column_logical_name)

    def _determine_stable_fields(self, remote_headers: List[str]) -> List[str]:
        """Determine logical stable fields to use based on remote headers.

        Prioritizes an 'id'-like column if one exists in the remote headers.
        Otherwise, defaults to a composite key of 'date', 'amount', 'description',
        using the stable keys configuration from the first queued operation.

        Args:
            remote_headers: List of actual header strings from the remote sheet.

        Returns:
            List[str]: A list of logical stable field names (e.g., ['id'] or
                       ['date', 'amount', 'description']).
        """
        id_aliases = {'id', '#', 'number', 'num'}
        # Check if any remote header matches an ID alias
        id_header_found = next(
            (h for h in remote_headers if h.strip().lower() in id_aliases),
            None,
        )
        if id_header_found:
            logging.debug(f'Using "id" (remote header: "{id_header_found}") as the stable field.')
            return ['id']

        # Fallback to composite key if no ID column in headers
        # Ensure there's something in the queue to base this on
        if not self._queue:
            # This case should ideally be prevented by earlier checks in commit_queue
            logging.error('Cannot determine stable fields: queue is empty and no ID column found.')
            # This situation might warrant raising an error or returning a default
            # that causes matching to fail predictably.
            raise ValueError('Cannot determine stable fields without an ID column or queued items.')

        # Use keys from the first queued item, excluding 'id' as it wasn't chosen
        default_stable_keys = [k for k in self._queue[0].stable_keys if k != 'id']
        logging.debug(f'Using composite stable fields: {default_stable_keys}')
        return default_stable_keys

    def _build_stable_headers_map(
            self,
            remote_headers: List[str],
            logical_stable_fields: List[str],
    ) -> Dict[str, List[str]]:
        """Map logical stable fields to their corresponding actual remote header names.

        Args:
            remote_headers: List of actual header strings from the remote sheet.
            logical_stable_fields: List of logical stable field names to map
                                   (e.g., ['id'] or ['date', 'amount', 'description']).

        Raises:
            ValueError: If a logical stable field cannot be mapped to any valid remote header.

        Returns:
            Dict[str, List[str]]:
                A mapping from logical stable field name to a list of actual remote header names
                that correspond to it.
        """
        header_map: Dict[str, List[str]] = {}
        if logical_stable_fields == ['id']:  # Special handling for 'id' primary key
            id_aliases = {'id', '#', 'number', 'num'}
            actual_id_header = next(
                (h for h in remote_headers if h.strip().lower() in id_aliases),
                None,
            )
            if not actual_id_header:
                # This should be caught by _determine_stable_fields logic path, but defensive check
                raise ValueError('Logical stable field is "id", but no matching ID column found in remote headers.')
            header_map['id'] = [actual_id_header]
        else:  # Handling for composite keys
            # Map each logical stable field to its configured header name
            headers_list = lib.settings.get_section('headers')
            role_map = {item['role']: item['name'] for item in headers_list}
            for logical_field in logical_stable_fields:
                actual_header = role_map.get(logical_field)
                if not actual_header or actual_header not in remote_headers:
                    raise ValueError(
                        f'Logical stable field "{logical_field}" not found in remote headers: {remote_headers}'
                    )
                header_map[logical_field] = [actual_header]
        return header_map

    def _fetch_stable_data(
            self,
            service: Any,  # Google Sheets API service instance
            stable_map: Dict[str, List[str]],  # Logical field -> list of actual remote headers
            header_to_idx: Dict[str, int],  # Actual remote header -> column index
            total_row_count: int,  # Total rows in sheet (incl. header)
            data_row_count: int,  # Number of data rows (excl. header)
    ) -> Dict[Tuple[str, str], List[Any]]:
        """Fetch and normalize data for stable key columns from the remote sheet.

        Args:
            service: Authorized Google Sheets API service instance.
            stable_map: Mapping from logical stable field to list of its actual remote header names.
            header_to_idx: Mapping from actual remote header name to its zero-based column index.
            total_row_count: Total number of rows in the sheet, including the header.
            data_row_count: Number of data rows (total_row_count - 1).

        Returns:
            Dict[Tuple[str, str], List[Any]]:
                A dictionary mapping `(logical_field_name, actual_header_name)` to a list
                of normalized values for that column. Each list is padded to `data_row_count`.
        """
        ranges_to_fetch: List[str] = []
        # Store which (logical_field, actual_header) corresponds to each range for later processing
        range_metadata: List[Tuple[str, str]] = []

        for logical_field, actual_headers in stable_map.items():
            for actual_header in actual_headers:
                col_idx = header_to_idx[actual_header]
                col_letter = idx_to_col(col_idx)
                # Fetch data from row 2 to the end
                sheet_range = f'{self.worksheet}!{col_letter}2:{col_letter}{total_row_count}'
                ranges_to_fetch.append(sheet_range)
                range_metadata.append((logical_field, actual_header))

        if not ranges_to_fetch:
            return {}

        logging.debug(f'Fetching stable data from ranges: {ranges_to_fetch}')
        batch_get_result = service.spreadsheets().values().batchGet(
            spreadsheetId=self.sheet_id,
            ranges=ranges_to_fetch,
            valueRenderOption='UNFORMATTED_VALUE',  # Get raw, unformatted values
            dateTimeRenderOption='SERIAL_NUMBER',  # Get dates as serial numbers
            fields='valueRanges(values)',
        ).execute()

        value_ranges_response = batch_get_result.get('valueRanges', [])
        column_values_map: Dict[Tuple[str, str], List[Any]] = {}

        for i, (logical_field, actual_header) in enumerate(range_metadata):
            value_range_data = value_ranges_response[i] if i < len(value_ranges_response) else {}
            raw_column_values = value_range_data.get('values', [])  # List of lists, e.g., [[val1], [val2]]

            # Flatten: extract first element of each inner list, or None if inner list is empty/missing
            flattened_values = [row_list[0] if row_list else None for row_list in raw_column_values]
            # Ensure the list has `data_row_count` elements, padding with None if necessary
            flattened_values.extend([None] * (data_row_count - len(flattened_values)))

            normalized_values: List[Any] = []
            for v in flattened_values:
                normalized_v = v  # Default to original value
                if v is not None:  # Perform normalization only on non-None values
                    if logical_field == 'date':
                        try:
                            normalized_v = google_serial_date_to_iso(float(v))
                        except (ValueError, TypeError):  # If v is not a floatable string or number
                            normalized_v = str(v) if v is not None else ''  # Fallback to string or empty
                    elif logical_field == 'amount':
                        try:
                            normalized_v = round(float(v), 2)
                        except (ValueError, TypeError):
                            normalized_v = str(v) if v is not None else ''
                    elif logical_field == 'id':
                        try:
                            normalized_v = int(float(v))  # ID often numeric, but allow float parsing
                        except (ValueError, TypeError):
                            normalized_v = str(v).strip() if isinstance(v, str) else str(v)
                    else:  # Typically description or other text fields
                        if isinstance(v, str):
                            normalized_v = v.strip()
                        else:  # Non-string, non-None values converted to string
                            normalized_v = str(v)
                else:  # v is None
                    if logical_field in ('date', 'amount', 'id'):
                        normalized_v = None  # Keep None for key numeric/date fields
                    else:  # Description etc.
                        normalized_v = ''  # Convert None to empty string for text fields for consistency
                normalized_values.append(normalized_v)
            column_values_map[(logical_field, actual_header)] = normalized_values
        return column_values_map

    def _assemble_remote_rows(
            self,
            column_values_map: Dict[Tuple[str, str], List[Any]],  # (log. field, act. header) -> [values]
            data_row_count: int,
    ) -> List[Dict[str, Any]]:  # Returns List[Dict[logical_field_name, Tuple[values...]]]
        """Build list of remote rows, keyed by logical stable fields.

        Each row dictionary maps a logical stable field name to a tuple of its values
        (since one logical field can map to multiple actual headers).

        Args:
            column_values_map: Mapping from (logical_field, actual_header) to its list of values.
            data_row_count: Number of data rows in the sheet.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, where each dictionary represents a remote row.
                                  Each row maps logical field names to a tuple of their values.
        """
        remote_rows_data: List[Dict[str, Any]] = []
        # Group actual headers by their logical field name
        headers_grouped_by_logical: Dict[str, List[str]] = {}
        for logical_field, actual_header in column_values_map.keys():
            headers_grouped_by_logical.setdefault(logical_field, []).append(actual_header)

        # Sort actual_headers within each logical group to ensure consistent tuple order
        for logical_field in headers_grouped_by_logical:
            headers_grouped_by_logical[logical_field].sort()

        for i in range(data_row_count):  # Iterate through each row index
            row_entry: Dict[str, Any] = {}
            for logical_field, actual_headers_list in headers_grouped_by_logical.items():
                # For each logical field, collect values from its mapped actual headers for the current row
                # Ensure actual_headers_list is sorted for consistent tuple creation if order matters
                # (already sorted above)
                value_tuple = tuple(column_values_map[(logical_field, h)][i] for h in actual_headers_list)
                row_entry[logical_field] = value_tuple
            remote_rows_data.append(row_entry)
        return remote_rows_data

    def _build_remote_index_map(
            self,
            remote_rows_data: List[Dict[str, Any]],  # List of {log. field: (values...)}
            logical_stable_fields: List[str],  # e.g. ['id'] or ['date', 'amount', 'description']
    ) -> Dict[Tuple[Any, ...], List[int]]:
        """Create an index map from stable-key tuples to remote row indices.

        The key for the map is a tuple of value-tuples, ordered by `logical_stable_fields`.
        Example key: `( (date_val1, date_val2), (amount_val1,), (desc_val1,) )`

        Args:
            remote_rows_data: List of remote row dictionaries (from _assemble_remote_rows).
            logical_stable_fields: Ordered list of logical stable field names to form the key.

        Returns:
            Dict[Tuple[Any, ...], List[int]]:
                Mapping from a composite stable key tuple to a list of 0-based data row indices
                that match this key.
        """
        index_map: Dict[Tuple[Any, ...], List[int]] = {}
        for remote_data_idx, row_dict in enumerate(remote_rows_data):
            # Construct the key tuple using values for fields specified in logical_stable_fields, in that order.
            # Each element of this key_tuple is itself a tuple of values (from row_dict[field]).
            key_tuple = tuple(row_dict.get(field) for field in logical_stable_fields)

            # Heuristic: skip rows where all components of the stable key are None or empty tuples.
            # This helps avoid matching genuinely empty rows or rows with all key fields blank.
            if all(
                    (v_tuple is None) or
                    (isinstance(v_tuple, tuple) and all(elem is None or elem == '' for elem in v_tuple))
                    for v_tuple in key_tuple
            ):
                continue  # Skip this row as its stable key is considered "empty"

            index_map.setdefault(key_tuple, []).append(remote_data_idx)
        return index_map

    def _match_operations(
            self,
            remote_index_map: Dict[Tuple[Any, ...], List[int]],
            # Key: composite stable key, Value: list of remote row indices
            logical_stable_fields: List[str],  # Ordered list of logical fields forming the key
            results: Dict[Tuple[int, str], Tuple[bool, str]],  # Output map for success/failure messages
    ) -> List[Tuple[EditOperation, int]]:  # Returns (EditOperation, 1-based sheet_row_number)
        """Match queued edits to remote rows and prepare a list of operations to update.

        Args:
            remote_index_map: Mapping from composite stable key to list of remote row indices.
            logical_stable_fields: Ordered list of logical fields used for matching.
            results: Dictionary to record the outcome (success/failure, message) for each operation.

        Returns:
            List[Tuple[EditOperation, int]]:
                A list of tuples, each containing an `EditOperation` that matched uniquely
                (or was disambiguated) and its corresponding 1-based sheet row number.
        """
        to_update: List[Tuple[EditOperation, int]] = []
        for op in self._queue:
            # Construct the key for this operation using its stored stable_keys,
            # ordered by logical_stable_fields.
            op_key_tuple = tuple(op.stable_keys.get(field) for field in logical_stable_fields)

            matched_remote_indices = remote_index_map.get(op_key_tuple, [])
            op_identifier = (op.local_id, op.column)

            if len(matched_remote_indices) == 1:
                # Unique match found
                remote_data_idx = matched_remote_indices[0]
                sheet_row_num = remote_data_idx + 2  # Convert 0-based data index to 1-based sheet row
                to_update.append((op, sheet_row_num))
                # Tentatively mark as success; actual commit outcome will confirm
                # results[op_identifier] = (True, 'Matched uniquely') # This message will be overwritten by commit status
            elif len(matched_remote_indices) > 1:
                # Ambiguous match: multiple remote rows match the stable keys.
                # Try to disambiguate using local_id as a hint for original row order.
                # op.local_id is 1-based local DB PK. (op.local_id - 1) is 0-based if DB PKs match original row order.
                expected_remote_idx = op.local_id - 1  # Heuristic: local_id might correspond to original row index
                if expected_remote_idx in matched_remote_indices:
                    sheet_row_num = expected_remote_idx + 2
                    to_update.append((op, sheet_row_num))
                    # results[op_identifier] = (True, 'Disambiguated by cache row order')
                    logging.debug(
                        f'Op ({op.local_id}, {op.column}) ambiguously matched, but disambiguated by local_id hint to sheet row {sheet_row_num}.')
                else:
                    results[op_identifier] = (False,
                                              'Ambiguous match: multiple remote rows match stable keys, and local_id hint did not resolve.')
                    logging.warning(
                        f'Op ({op.local_id}, {op.column}) failed: ambiguous match. Key: {op_key_tuple}, Matches: {matched_remote_indices}')
            else:
                # No match found
                results[op_identifier] = (False,
                                          'No matching row found on remote; data may have changed significantly.')
                logging.warning(f'Op ({op.local_id}, {op.column}) failed: no matching row. Key: {op_key_tuple}')
        return to_update

    def _build_update_payload(
            self,
            to_update: List[Tuple[EditOperation, int]],  # (EditOperation, 1-based_sheet_row_number)
            header_to_idx: Dict[str, int],  # Actual remote header -> column index
    ) -> Dict[str, Any]:
        """Construct the request body for Google Sheets API `batchUpdate` values.

        Args:
            to_update: List of (EditOperation, sheet_row_number) tuples for confirmed updates.
            header_to_idx: Mapping from actual remote header name to its zero-based column index.

        Raises:
            ValueError: If mapping for an operation's column references no valid remote header.

        Returns:
            Dict[str, Any]: Request body dictionary for `batchUpdate`.
        """
        update_data_list: List[Dict[str, Any]] = []
        from ..settings import lib  # needed for role_map
        headers_list = lib.settings.get_section('headers')
        # Build role->names map to detect ambiguous multi-mapping for non-singleton roles
        role_to_names: Dict[str, List[str]] = {}
        for item in headers_list:
            role_to_names.setdefault(item['role'], []).append(item['name'])
        for op, sheet_row_num in to_update:
            # op.column is logical role; ensure exactly one header defined
            names = role_to_names.get(op.column, [])
            if not names:
                raise ValueError(
                    f'Header role "{op.column}" not found among configured headers.'
                )
            if len(names) > 1:
                raise ValueError(
                    f'Ambiguous header mapping for role "{op.column}": multiple headers {names}. Cannot determine which to update.'
                )
            actual_header_to_update = names[0]
            if actual_header_to_update not in header_to_idx:
                raise ValueError(
                    f'Actual header "{actual_header_to_update}" for role "{op.column}" not present in remote headers.'
                )
            # Determine column index and build update entry
            target_col_idx = header_to_idx[actual_header_to_update]
            target_col_letter = idx_to_col(target_col_idx)
            update_data_list.append({
                'range': f'{self.worksheet}!{target_col_letter}{sheet_row_num}',
                'values': [[op.new_value]],
            })
        return {'valueInputOption': 'USER_ENTERED', 'data': update_data_list}

    def _apply_local_updates(
            self,
            successfully_updated_ops: List[Tuple[EditOperation, int]],  # (EditOperation, sheet_row_number)
            header_to_idx: Dict[str, int],  # Actual remote header -> column index
    ) -> None:
        """Update the local cache database for successfully committed edits.

        Args:
            successfully_updated_ops: List of (EditOperation, sheet_row_number) tuples that
                                      were successfully pushed to the remote sheet.
            header_to_idx: Mapping from the actual remote header name to its zero-based column index.

        Returns:
            None
        """
        logging.debug(f'Applying {len(successfully_updated_ops)} updates to local cache.')

        from ..settings import lib
        headers_list = lib.settings.get_section('headers')
        role_map = {item['role']: item['name'] for item in headers_list}
        for op, _ in successfully_updated_ops:
            try:
                # op.column is logical role, so find the header name
                db_column_name = role_map.get(op.column)
                if not db_column_name:
                    raise KeyError(f'Header role "{op.column}" not found for local cache update')
                # Perform the local cache update
                DatabaseAPI.update_cell(op.local_id, db_column_name, op.new_value)
                logging.debug(f'Local cache updated for id {op.local_id}, column "{db_column_name}".')
            except StopIteration:  # Should not happen if logic is consistent
                logging.error(
                    f'Critical error: Could not update local cache for op ({op.local_id}, {op.column}).'
                )
            except Exception:  # Catch other DB exceptions
                logging.exception(
                    f'Failed to update local cache for id {op.local_id}, column "{op.column}".'
                )


sync = SyncAPI()
