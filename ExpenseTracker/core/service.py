"""
Google Sheets Service Module.

Provides functions to load ledger configuration, authenticate with Google Sheets,
and retrieve the specified worksheet as a pandas DataFrame and its headers asynchronously.
"""

import logging
import re
import socket
import ssl
import string
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import pandas as pd
from PySide6 import QtCore, QtWidgets
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..status import status

TOTAL_TIMEOUT: int = 180
MAX_RETRIES: int = 6
BATCH_SIZE: int = 3000  # Number of rows per batch for large sheets


class AsyncWorker(QtCore.QThread):
    """
    Generic worker that runs a blocking function in a QThread with retry logic.

    Emits:
      - resultReady(object): with the function's result on success.
      - errorOccurred(str): with an error message on failure.
    """
    resultReady = QtCore.Signal(object)
    errorOccurred = QtCore.Signal(str)

    def __init__(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.func = func
        self.args = args
        # Retry parameters centralized here.
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
            except (
                    status.AuthenticationExceptionException,
                    status.CredsNotFoundException,
                    status.CredsInvalidException,
                    status.SpreadsheetIdNotConfiguredException,
                    status.SpreadsheetWorksheetNotConfiguredException,
                    status.HeadersInvalidException,
                    status.HeaderMappingInvalidException
            ) as ex:
                self.errorOccurred.emit(str(ex))
                return
            except Exception as ex:
                last_exception = ex
                time.sleep(self.wait_seconds)
        self.errorOccurred.emit(str(last_exception))


class SheetsFetchProgressDialog(QtWidgets.QDialog):
    """
    Generic progress dialog for asynchronous operations.

    Emits:
      - cancelled: when the user cancels the operation.
    """
    cancelled = QtCore.Signal()

    def __init__(self, total_timeout: int = TOTAL_TIMEOUT, parent: Optional[QtWidgets.QWidget] = None,
                 status_text: str = 'Fetching data.') -> None:
        super().__init__(parent)
        self.total_timeout: int = total_timeout
        self.remaining: int = total_timeout
        self.setWindowTitle('Fetching Data')
        self.setModal(True)
        self.countdown_timer = QtCore.QTimer(self)
        self.countdown_timer.setInterval(1000)
        from ..ui import ui  # Retaining original import style.
        ui.set_stylesheet(self)
        self.status_text: str = status_text
        self._create_ui()
        self._connect_signals()

    def showEvent(self, event: QtCore.QEvent) -> None:
        self.countdown_timer.start()

    def _create_ui(self) -> None:
        from ..ui import ui

        QtWidgets.QVBoxLayout(self)
        margin = ui.Size.Margin(1.0)
        self.layout().setContentsMargins(margin, margin, margin, margin)
        self.layout().setSpacing(ui.Size.Indicator(1.0))

        self.status_label = QtWidgets.QLabel(self.status_text)
        self.layout().addWidget(self.status_label, 1)
        self.countdown_label = QtWidgets.QLabel(f'Please wait ({self.remaining}s).')
        self.layout().addWidget(self.countdown_label, 1)

        self.layout().addSpacing(margin)

        self.cancel_button = QtWidgets.QPushButton('Cancel')
        self.layout().addWidget(self.cancel_button, 1)

    def _connect_signals(self) -> None:
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.cancel_button.clicked.connect(self.on_cancel)
        self.accepted.connect(self.on_cancel)

    @QtCore.Slot()
    def update_countdown(self) -> None:
        self.remaining -= 1
        self.countdown_label.setText(f'Please wait ({self.remaining}s)...')
        if self.remaining <= 0:
            self.countdown_timer.stop()
            self.countdown_label.setText('Operation timed out.')

    @QtCore.Slot()
    def on_cancel(self) -> None:
        self.cancelled.emit()
        self.reject()


def get_service() -> Any:
    """
    Builds and returns a Google Sheets service client.

    Returns:
        The Sheets API Resource.
    """
    from . import auth
    creds: Any = auth.get_creds()
    try:
        service: Any = build('sheets', 'v4', credentials=creds)
        logging.info('Google Sheets service client created successfully.')
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
        WorksheetNotFoundException: If the worksheet does not exist.
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

    logging.info('Connecting to Google Sheets API...')
    try:
        result: Dict[str, Any] = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields='sheets(properties(title,gridProperties(rowCount,columnCount)))'
        ).execute()
        logging.info(f'Access confirmed for spreadsheet "{spreadsheet_id}".')
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
        raise status.UnknownException('No result returned from the API.')

    worksheet_name: Optional[str] = config.get('worksheet', None)
    if not worksheet_name:
        raise status.SpreadsheetWorksheetNotConfiguredException

    sheet: Optional[Dict[str, Any]] = next(
        (s for s in result.get('sheets', [])
         if s.get('properties', {}).get('title', '') == worksheet_name), None)
    if not sheet:
        raise status.WorksheetNotFoundException(
            f'Worksheet "{worksheet_name}" not found in spreadsheet "{spreadsheet_id}".')

    logging.info(f'Worksheet "{worksheet_name}" found in spreadsheet "{spreadsheet_id}".')
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

    logging.info(
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

    config_headers: List[str] = []
    for k, v in config.items():
        j: str = '\\'.join(lib.DATA_MAPPING_SEPARATOR_CHARS)
        for _v in re.split(fr'[\{j}]', v):
            if k not in config_headers:
                config_headers.append(_v)

    config_headers_set: Set[str] = set(sorted(config_headers))
    logging.info(f'Header mapping configuration found {len(config_headers_set)} columns.')

    remote_headers: List[str] = remote_headers or _fetch_headers()
    remote_headers_set: Set[str] = set(sorted(remote_headers))

    if not config_headers_set.issubset(remote_headers_set):
        raise status.HeaderMappingInvalidException(
            f'Header mapping is referencing columns not found in the remote sheet: '
            f'{", ".join(config_headers_set.difference(remote_headers_set))}.'
        )

    logging.info(
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
    logging.info(f'date="{date_column}" is of accepted type "{_type}".')

    amount_column: str = config.get('amount')
    _type = config_headers_full[amount_column]
    if _type not in ('float', 'int'):
        raise status.HeaderMappingInvalidException(
            f'Amount column source must be a numeric type, but column "{amount_column}" is of type "{_type}".'
        )
    logging.info(f'amount="{amount_column}" is of accepted type "{_type}".')
    logging.info(f'Header mapping verified successfully. Found {len(config_headers_full)} columns.')


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

    last_col: str = string.ascii_uppercase[col_count - 1]
    data_ranges: List[str] = []
    data_start: int = 1
    while data_start <= row_count:
        data_end: int = min(data_start + BATCH_SIZE - 1, row_count)
        data_ranges.append(f'{worksheet_name}!A{data_start}:{last_col}{data_end}')
        data_start = data_end + 1

    logging.info(f'Fetching data rows 1-{row_count} in batches.')
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
    logging.info(f'Total data rows fetched: {len(data_rows)}.')

    header: List[Any] = data_rows.pop(0) if data_rows else []
    df: pd.DataFrame = pd.DataFrame(data_rows, columns=header)

    logging.info(f'Constructed DataFrame: {df.shape[0]} rows x {df.shape[1]} columns from sheet "{worksheet_name}".')

    _verify_mapping()
    _verify_headers(remote_headers=header)

    return df


def fetch_data(total_timeout: int = TOTAL_TIMEOUT) -> pd.DataFrame:
    """
    Asynchronously fetches ledger data as a pandas DataFrame.
    """
    data = start_asynchronous(_fetch_data, total_timeout=total_timeout, status_text='Fetching data.')

    from ..ui.actions import signals
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
    end_col: str = string.ascii_uppercase[col_count - 1]
    range_ = f'{worksheet_name}!A1:{end_col}1'

    logging.info(f'Fetching headers from range "{range_}".')
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
    logging.info(f'Total header rows fetched: {len(data_rows)}.')

    if not data_rows:
        raise status.UnknownException('No data found in the remote sheet.')
    header_row: List[Any] = data_rows[0] if data_rows[0] else []
    header_row = [str(cell) for cell in header_row]
    logging.info(f'Found {len(header_row)} headers in the remote sheet: [{",".join(sorted(header_row))}].')
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

    logging.info('Fetching categories from the remote sheet...')
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
    column_letter: str = string.ascii_uppercase[idx]
    range_: str = f'{worksheet_name}!{column_letter}2:{column_letter}'

    logging.info(f'Fetching categories from range "{range_}".')
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
    logging.info(f'Total data rows fetched: {len(data_rows)}.')

    if not data_rows:
        raise status.UnknownException('No data found in the remote sheet.')

    categories: List[str] = sorted({row[0] for row in data_rows if row and row[0]})
    logging.info(f'Found {len(categories)} unique categories: [{",".join(categories)}].')
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
    dialog: SheetsFetchProgressDialog = SheetsFetchProgressDialog(total_timeout=total_timeout,
                                                                  status_text=status_text)
    worker: AsyncWorker = AsyncWorker(func, *args, **kwargs)
    result: Dict[str, Any] = {'data': None, 'error': None}
    loop: QtCore.QEventLoop = QtCore.QEventLoop()

    worker.resultReady.connect(lambda d: (result.update({'data': d}), loop.quit()))
    worker.errorOccurred.connect(lambda err: (result.update({'error': err}), loop.quit()))
    dialog.cancelled.connect(lambda: loop.quit())

    worker.start()
    dialog.show()

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
        raise Exception(result['error'])
    return result['data']
