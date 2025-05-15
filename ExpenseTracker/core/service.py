"""Google Sheets API integration with asynchronous operations.

Provides methods to authenticate, fetch, and verify Google Sheets data (headers, rows, categories)
using asynchronous workers and progress dialogs.
"""

import logging
import socket
import ssl
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pandas as pd
from PySide6 import QtCore, QtWidgets
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import auth_manager, AuthExpiredError
from ..status import status
from ..ui.ui import BaseProgressDialog

# Cached Sheets API client to avoid repeated discovery/auth costs
_cached_service: Any = None

TOTAL_TIMEOUT: int = 180
MAX_RETRIES: int = 6
BATCH_SIZE: int = 3000  # Number of rows per batch for large sheets


class AsyncWorker(QtCore.QThread):
    """
    Generic worker thread with retry logic for blocking functions.

    Signals:
        resultReady (object): Emitted with the function's result on success.
        errorOccurred (str): Emitted with an error message on failure.
    """
    resultReady = QtCore.Signal(object)
    errorOccurred = QtCore.Signal(object)

    def __init__(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.func = func
        self.args = args

        self.max_attempts = kwargs.pop('max_attempts', MAX_RETRIES)
        self.wait_seconds = kwargs.pop('wait_seconds', 2.0)
        self.kwargs = kwargs

    def run(self) -> None:
        attempts = 0
        last_exception = None
        while attempts < self.max_attempts:
            attempts += 1
            try:
                result = self.func(*self.args, **self.kwargs)
                self.resultReady.emit(result)
                return
            except AuthExpiredError as ex:
                # Notify GUI that interactive authentication is required
                from ..ui.actions import signals
                signals.authenticationRequested.emit()
                self.errorOccurred.emit(ex)
                return
            except (
                    status.AuthenticationExceptionException,
                    status.CredsNotFoundException,
                    status.CredsInvalidException,
                    status.SpreadsheetIdNotConfiguredException,
                    status.SpreadsheetWorksheetNotConfiguredException,
                    status.HeadersInvalidException,
                    status.HeaderMappingInvalidException
            ) as ex:
                self.errorOccurred.emit(ex)
                return
            except Exception as ex:
                last_exception = ex
                time.sleep(self.wait_seconds)
        # All retries exhausted
        self.errorOccurred.emit(last_exception)


class SheetsFetchProgressDialog(BaseProgressDialog):
    """
    Progress dialog for asynchronous API operations.

    Signals:
        cancelled (): Emitted when the user cancels the operation.
    """

    def __init__(self, total_timeout: int = TOTAL_TIMEOUT,
                 status_text: str = 'Fetching data.') -> None:
        super().__init__(total_timeout, status_text)

    def _populate_content(self, layout: QtWidgets.QVBoxLayout) -> None:
        from ..ui import ui

        self.status_label = QtWidgets.QLabel(self.status_text)
        layout.addWidget(self.status_label, 1)

        self.error_label = QtWidgets.QLabel('')
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(
            f'color: {ui.Color.Red(qss=True)};'
        )
        layout.addWidget(self.error_label, 1)

        self.countdown_label = QtWidgets.QLabel(
            f'Please wait ({self.remaining}s).'
        )
        layout.addWidget(self.countdown_label, 1)

        layout.addSpacing(ui.Size.Margin(1.0))

        self.cancel_button = QtWidgets.QPushButton('Cancel')
        layout.addWidget(self.cancel_button, 1)

    def _connect_signals(self) -> None:
        super()._connect_signals()

        self.accepted.connect(self.on_cancel)
        from ..ui.actions import signals
        signals.error.connect(self.on_error)

    @QtCore.Slot(str)
    def on_error(self, msg: str) -> None:
        """Update the error label with a new error message."""
        self.error_label.setText(msg)
        QtWidgets.QApplication.processEvents()

    def _update_countdown_label(self) -> None:
        """Update countdown label each second."""
        self.countdown_label.setText(f'Please wait ({self.remaining}s)...')

    @QtCore.Slot()
    def on_timeout(self) -> None:
        """Handle timeout: stop timer and show timeout message."""
        self.countdown_timer.stop()
        self.countdown_label.setText('Operation timed out.')


def clear_service() -> None:
    """
    Clears the cached Sheets API client.
    """
    global _cached_service

    try:
        if _cached_service:
            _cached_service.close()
    except Exception as ex:
        logging.debug(f'Failed closing cached Sheets service client: {ex}')

    _cached_service = None


def get_service() -> Any:
    """
    Builds (or returns cached) Google Sheets service client.

    Returns:
        The Sheets API Resource, reusing a single client per app run.
    """
    global _cached_service
    # Obtain valid credentials (non-interactive, may raise AuthExpiredError)
    logging.debug(
        f"[Thread-{threading.get_ident()}] get_service: invoking auth_manager.get_valid_credentials at {time.time()}")
    creds: Any = auth_manager.get_valid_credentials()
    logging.debug(
        f"[Thread-{threading.get_ident()}] get_service: returned from auth_manager.get_valid_credentials at {time.time()}")
    # Return cached client if already created
    if _cached_service is not None:
        return _cached_service
    try:
        service: Any = build('sheets', 'v4', credentials=creds)
        logging.debug('Google Sheets service client created successfully.')
        _cached_service = service
        return service
    except Exception as ex:
        raise status.ServiceUnavailableException from ex


def _convert_types(cell: Optional[Dict[str, Any]]) -> str:
    """
    Converts the source cell to a mapped type.

    Returns:
        'date' if DATE or DATE_TIME, 'int' or 'float' for numeric types, otherwise 'string'.
    """
    if not cell:
        return 'string'
    fmt_type: str = cell.get('userEnteredFormat', {}).get('numberFormat', {}).get('type', '')
    if fmt_type in ('DATE', 'DATE_TIME'):
        return 'date'
    if fmt_type in ('NUMBER', 'CURRENCY', 'PERCENT', 'SCIENTIFIC'):
        number_val: Optional[float] = cell.get('effectiveValue', {}).get('numberValue')
        if number_val is not None and number_val == int(number_val):
            return 'int'
        return 'float'
    return 'string'


def _query_sheet_size(service: Any, spreadsheet_id: str, worksheet_name: str) -> Tuple[int, int]:
    """
    Queries the worksheet's grid size.

    Args:
        service: The Sheets API resource.
        spreadsheet_id (str): Spreadsheet ID.
        worksheet_name (str): Worksheet title.

    Returns:
        A tuple (row_count, column_count).

    Raises:
        WorksheetNotFoundException: If the worksheet doesn't exist.
    """
    result: Dict[str, Any] = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields='sheets(properties(title,gridProperties(rowCount,columnCount)))'
    ).execute()

    sheet: Optional[Dict[str, Any]] = next(
        (s for s in result.get('sheets', [])
         if s.get('properties', {}).get('title', '') == worksheet_name), None)
    if not sheet:
        raise status.WorksheetNotFoundException(f'Worksheet "{worksheet_name}" not found.')
    grid_props: Dict[str, Any] = sheet.get('properties', {}).get('gridProperties', {})
    row_count: int = grid_props.get('rowCount', 0)
    column_count: int = grid_props.get('columnCount', 0)
    return row_count, column_count


def _verify_sheet_access() -> Any:
    """
    Verifies access to the Google Sheets API and checks if the specified spreadsheet
    exists and is accessible.

    Returns:
        The Sheets API Resource.

    Raises:
        SpreadsheetIdNotConfiguredException, ServiceUnavailableException,
        SpreadsheetWorksheetNotConfiguredException, WorksheetNotFoundException.
    """
    from ..settings import lib

    service: Any = get_service()
    config: Dict[str, Any] = lib.settings.get_section('spreadsheet')
    spreadsheet_id: Optional[str] = config.get('id', None)
    if not spreadsheet_id:
        raise status.SpreadsheetIdNotConfiguredException

    logging.debug('Connecting to Google Sheets API...')
    try:
        result: Dict[str, Any] = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields='sheets(properties(title,gridProperties(rowCount,columnCount)))'
        ).execute()
        logging.debug(f'Access confirmed for spreadsheet "{spreadsheet_id}".')
    except HttpError as ex:
        stat: Optional[int] = ex.resp.status if ex.resp else None
        if stat == 404:
            raise status.ServiceUnavailableException(
                f'Spreadsheet "{spreadsheet_id}" not found (HTTP 404).'
            ) from ex
        elif stat == 403:
            raise status.ServiceUnavailableException(
                f'Access denied (HTTP 403) for spreadsheet "{spreadsheet_id}". '
                'Please share the sheet with your authenticated Google account.'
            ) from ex
        else:
            raise status.ServiceUnavailableException(
                f'Error accessing spreadsheet "{spreadsheet_id}": {ex}'
            ) from ex
    except socket.timeout as ex:
        raise status.ServiceUnavailableException(f'Timeout error fetching data: {ex}') from ex
    except ssl.SSLError as ex:
        raise status.ServiceUnavailableException(f'SSL error fetching data: {ex}') from ex

    if not result:
        # No response from Sheets API: service unavailable
        raise status.ServiceUnavailableException('No result returned from the Sheets API.')

    worksheet_name: Optional[str] = config.get('worksheet', None)
    if not worksheet_name:
        raise status.SpreadsheetWorksheetNotConfiguredException

    sheet: Optional[Dict[str, Any]] = next(
        (s for s in result.get('sheets', [])
         if s.get('properties', {}).get('title', '') == worksheet_name), None)
    if not sheet:
        raise status.WorksheetNotFoundException(
            f'Worksheet "{worksheet_name}" not found in spreadsheet "{spreadsheet_id}".')

    logging.debug(f'Worksheet "{worksheet_name}" found in spreadsheet "{spreadsheet_id}".')
    return service


def verify_sheet_access(total_timeout: int = TOTAL_TIMEOUT) -> Any:
    """
    Asynchronously verifies access to the spreadsheet, returning the Sheets API resource.
    """
    return start_asynchronous(_verify_sheet_access, total_timeout=total_timeout,
                              status_text='Verifying sheet access.')


def _verify_headers(remote_headers: List[str] = None) -> Set[str]:
    """
    Verify the headers of the remote spreadsheet against the local configuration.
    """
    from ..settings import lib

    config: Dict[str, Any] = lib.settings.get_section('header')
    if not config:
        raise status.HeadersInvalidException

    remote_headers = remote_headers or _fetch_headers()

    if not remote_headers:
        raise status.HeadersInvalidException('No data found in the remote sheet.')

    remote_headers_set = set(sorted(remote_headers))
    expected_headers = set(sorted(config.keys()))
    mismatch = expected_headers.difference(remote_headers_set)

    if mismatch:
        raise status.HeadersInvalidException(
            f'Remote sheet headers do not match the expected configuration: '
            f'{", ".join(mismatch)} not found.'
        )

    logging.debug(
        f'Found {len(expected_headers)} headers in the local configuration: '
        f'[{",".join(sorted(expected_headers))}].'
    )
    return remote_headers_set


def verify_headers(total_timeout: int = TOTAL_TIMEOUT) -> Set[str]:
    """
    Asynchronously verifies the headers of the remote spreadsheet.
    """
    return start_asynchronous(_verify_headers, total_timeout=total_timeout,
                              status_text='Verifying headers.')


def _verify_mapping(remote_headers: List[str] = None) -> None:
    """
    Verify the header mapping configuration against the remote spreadsheet's column values.
    """
    from ..settings import lib

    config: Dict[str, Any] = lib.settings.get_section('mapping')
    if not config:
        raise status.HeaderMappingInvalidException

    # Build the list of header names referenced by mapping (split merged specs)                                                                                                                               │
    config_headers: List[str] = []
    from ..settings.lib import parse_merge_mapping
    for raw_spec in config.values():
        for hdr in parse_merge_mapping(raw_spec):
            if hdr not in config_headers:
                config_headers.append(hdr)

    config_headers_set: Set[str] = set(config_headers)
    logging.debug(f'Header mapping configuration found {len(config_headers_set)} columns.')

    remote_headers: List[str] = remote_headers or _fetch_headers()
    remote_headers_set: Set[str] = set(sorted(remote_headers))

    if not config_headers_set.issubset(remote_headers_set):
        raise status.HeaderMappingInvalidException(
            f'Header mapping is referencing columns not found in the remote sheet: '
            f'{", ".join(config_headers_set.difference(remote_headers_set))}.'
        )

    logging.debug(
        f'Header mapping references {len(config_headers_set)} valid columns: '
        f'[{",".join(sorted(config_headers_set))}].'
    )

    config_headers_full: Dict[str, Any] = lib.settings.get_section('header')
    date_column: str = config.get('date')
    _type: str = config_headers_full[date_column]
    if _type != 'date':
        raise status.HeaderMappingInvalidException(
            f'Date column source must be a date type, but column "{date_column}" is of type "{_type}".'
        )
    logging.debug(f'date="{date_column}" is of accepted type "{_type}".')

    amount_column: str = config.get('amount')
    _type = config_headers_full[amount_column]
    if _type not in ('float', 'int'):
        raise status.HeaderMappingInvalidException(
            f'Amount column source must be a numeric type, but column "{amount_column}" is of type "{_type}".'
        )
    logging.debug(f'amount="{amount_column}" is of accepted type "{_type}".')
    logging.debug(f'Header mapping verified successfully. Found {len(config_headers_full)} columns.')


def verify_mapping(total_timeout: int = TOTAL_TIMEOUT) -> None:
    """
    Asynchronously verifies the header mapping configuration against the remote spreadsheet's column values.
    """
    return start_asynchronous(_verify_mapping, total_timeout=total_timeout,
                              status_text='Verifying header mapping.')


def _fetch_data(
        value_render_option: str = 'UNFORMATTED_VALUE'
) -> pd.DataFrame:
    """
    Retrieves ledger data as a pandas DataFrame using the spreadsheet configuration.

    Returns:
        A pandas DataFrame containing the ledger data.
    """
    from ..settings import lib

    config: Dict[str, Any] = lib.settings.get_section('spreadsheet')

    spreadsheet_id: Optional[str] = config.get('id', None)
    if not spreadsheet_id:
        raise status.SpreadsheetIdNotConfiguredException

    worksheet_name: Optional[str] = config.get('worksheet', None)
    if not worksheet_name:
        raise status.SpreadsheetWorksheetNotConfiguredException

    service: Any = _verify_sheet_access()

    row_count, col_count = _query_sheet_size(service, spreadsheet_id, worksheet_name)
    if row_count < 2:
        logging.warning(f'No data rows found in "{worksheet_name}".')
        return pd.DataFrame()

    from .sync import idx_to_col
    last_col: str = idx_to_col(col_count - 1)
    data_ranges: List[str] = []
    data_start: int = 1
    while data_start <= row_count:
        data_end: int = min(data_start + BATCH_SIZE - 1, row_count)
        data_ranges.append(f'{worksheet_name}!A{data_start}:{last_col}{data_end}')
        data_start = data_end + 1

    logging.debug(f'Fetching data rows 1-{row_count} in batches.')
    batch_result: Dict[str, Any] = service.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=data_ranges,
        valueRenderOption=value_render_option,
        fields='valueRanges(values)'
    ).execute()

    data_rows: List[List[Any]] = []
    for vr in batch_result.get('valueRanges', []):
        values: List[List[Any]] = vr.get('values', [])
        if values:
            data_rows.extend(values)
    logging.debug(f'Total data rows fetched: {len(data_rows)}.')

    header: List[Any] = data_rows.pop(0) if data_rows else []
    df: pd.DataFrame = pd.DataFrame(data_rows, columns=header)

    logging.debug(f'Constructed DataFrame: {df.shape[0]} rows x {df.shape[1]} columns from sheet "{worksheet_name}".')

    _verify_mapping()
    _verify_headers(remote_headers=header)

    return df


def fetch_data(total_timeout: int = TOTAL_TIMEOUT) -> pd.DataFrame:
    """
    Asynchronously fetches ledger data as a pandas DataFrame.
    """
    from ..ui.actions import signals

    signals.dataAboutToBeFetched.emit()
    data = start_asynchronous(_fetch_data, total_timeout=total_timeout, status_text='Fetching data.')
    signals.dataFetched.emit(data.copy())


def _fetch_headers(
        value_render_option: str = 'UNFORMATTED_VALUE'
) -> List[str]:
    """
    Retrieves the header row from the remote sheet's worksheet.

    Returns:
        A list of header names.

    Raises:
        Various exceptions if not properly configured or data not found.
    """
    from ..settings import lib

    config: Dict[str, Any] = lib.settings.get_section('spreadsheet')

    spreadsheet_id: Optional[str] = config.get('id', None)
    if not spreadsheet_id:
        raise status.SpreadsheetIdNotConfiguredException

    worksheet_name: Optional[str] = config.get('worksheet', None)
    if not worksheet_name:
        raise status.SpreadsheetWorksheetNotConfiguredException

    service: Any = _verify_sheet_access()

    _, col_count = _query_sheet_size(service, spreadsheet_id, worksheet_name)
    from .sync import idx_to_col
    end_col: str = idx_to_col(col_count - 1)
    range_ = f'{worksheet_name}!A1:{end_col}1'

    logging.debug(f'Fetching headers from range "{range_}".')
    batch_result: Dict[str, Any] = service.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=[range_],
        valueRenderOption=value_render_option,
        fields='valueRanges(values)'
    ).execute()

    data_rows: List[List[Any]] = []
    for vr in batch_result.get('valueRanges', []):
        values: List[List[Any]] = vr.get('values', [])
        if values:
            data_rows.extend(values)

    logging.debug(f'Total header rows fetched: {len(data_rows)}.')

    if not data_rows:
        logging.warning(f'The remote sheet is empty!')
        return data_rows

    header_row: List[Any] = data_rows[0] if data_rows[0] else []
    header_row = [str(cell) for cell in header_row]
    logging.debug(f'Found {len(header_row)} headers in the remote sheet: [{",".join(sorted(header_row))}].')
    return header_row


def fetch_headers(total_timeout: int = TOTAL_TIMEOUT) -> List[str]:
    """
    Asynchronously fetches the header row.
    """
    return start_asynchronous(_fetch_headers, total_timeout=total_timeout, status_text='Fetching headers.')


def _fetch_categories(
        value_render_option: str = 'UNFORMATTED_VALUE'
) -> List[str]:
    """
    Fetches a unique list of categories from the remote spreadsheet.

    Returns:
        A sorted list of unique category values.
    """
    from ..settings import lib

    logging.debug('Fetching categories from the remote sheet...')
    service: Any = _verify_sheet_access()
    _verify_mapping()

    config: Dict[str, Any] = lib.settings.get_section('mapping')
    category_column: Optional[str] = config.get('category', None)
    if not category_column:
        raise status.HeaderMappingInvalidException('Category column not found in mapping.')

    spreadsheet_id: Optional[str] = lib.settings.get_section('spreadsheet').get('id')
    worksheet_name: Optional[str] = lib.settings.get_section('spreadsheet').get('worksheet')

    headers = lib.settings.get_section('header').keys()
    header_names: List[str] = list(headers)
    if category_column not in header_names:
        raise status.HeaderMappingInvalidException(f'Category "{category_column}" not found.')

    idx: int = header_names.index(category_column)
    from .sync import idx_to_col
    column_letter: str = idx_to_col(idx)
    range_: str = f'{worksheet_name}!{column_letter}2:{column_letter}'

    logging.debug(f'Fetching categories from range "{range_}".')
    batch_result: Dict[str, Any] = service.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=[range_],
        valueRenderOption=value_render_option,
        fields='valueRanges(values)'
    ).execute()

    data_rows: List[List[Any]] = []
    for vr in batch_result.get('valueRanges', []):
        values: List[List[Any]] = vr.get('values', [])
        if values:
            data_rows.extend(values)
    logging.debug(f'Total data rows fetched: {len(data_rows)}.')

    if not data_rows:
        # No category data: treat as empty spreadsheet
        raise status.SpreadsheetEmptyException('No data found in the remote sheet.')

    categories: List[str] = sorted({row[0] for row in data_rows if row and row[0]})
    logging.debug(f'Found {len(categories)} unique categories: [{",".join(categories)}].')
    return categories


def fetch_categories(total_timeout: int = TOTAL_TIMEOUT) -> List[str]:
    """
    Asynchronously fetches the unique list of categories.
    """
    return start_asynchronous(_fetch_categories, total_timeout=total_timeout, status_text='Fetching categories.')


def start_asynchronous(func: Callable[..., Any], *args: Any, total_timeout: int = TOTAL_TIMEOUT,
                       status_text: str = 'Fetching data.', **kwargs: Any) -> Any:
    """
    Generic asynchronous operation wrapper.

    Creates and runs an AsyncWorker with a progress dialog and event loop.

    Args:
        func: The blocking function to run.
        *args, **kwargs: Arguments passed to func.
        total_timeout (int): Total operation timeout.
        status_text (str): Label displayed in the progress dialog.

    Returns:
        The result of the function on success.

    Raises:
        Exception: If the operation is cancelled, times out, or an error occurs.
    """
    dialog: SheetsFetchProgressDialog = SheetsFetchProgressDialog(
        total_timeout,
        status_text=status_text,
    )
    worker: AsyncWorker = AsyncWorker(func, *args, **kwargs)

    result: Dict[str, Any] = {'data': None, 'error': None}
    loop: QtCore.QEventLoop = QtCore.QEventLoop()

    worker.errorOccurred.connect(
        lambda err: dialog.errorOccurred.emit(str(err)),
        QtCore.Qt.QueuedConnection
    )
    worker.resultReady.connect(lambda d: (result.update({'data': d}), loop.quit()))
    worker.errorOccurred.connect(lambda err: (result.update({'error': err}), loop.quit()))
    dialog.cancelled.connect(lambda: loop.quit())

    worker.start()
    dialog.open()

    timer: QtCore.QTimer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.setInterval(total_timeout * 1000)
    timer.timeout.connect(lambda: (dialog.countdown_timer.stop(), loop.quit()))
    timer.start()
    loop.exec()

    if worker.isRunning():
        worker.terminate()
        worker.wait()
        raise Exception('Operation cancelled or timed out.')
    dialog.close()
    if result['error']:
        err = result['error']
        from ..status import status
        from ..ui.actions import signals

        # Propagate known status exceptions directly
        if isinstance(err, status.BaseStatusException):
            raise err

        # If authentication expired, notify GUI and raise authentication exception
        if isinstance(err, AuthExpiredError) or isinstance(err, status.AuthenticationExceptionException):
            if signals:
                signals.authenticationRequested.emit()
            raise status.AuthenticationExceptionException(str(err))

        # Unknown errors
        raise status.UnknownException(str(err))
    return result['data']


# Reset cached Sheets API client when credentials/config change
try:
    from ..ui.actions import signals


    @QtCore.Slot(str)
    def _reset_cached_service(section: str) -> None:
        """Clear the cached Sheets client when client_secret changes."""
        if section == 'client_secret':
            logging.debug('Clearing cached Sheets service client due to client_secret change')
            global _cached_service
            _cached_service = None


    signals.configSectionChanged.connect(_reset_cached_service)
except ImportError:
    # UI signals not available
    pass
