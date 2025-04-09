"""
Google Sheets Service Module.

Provides functions to load ledger configuration, authenticate with Google Sheets,
and retrieve the specified worksheet as a pandas DataFrame and its headers asynchronously.
"""

import logging
import socket
import ssl
import string
import time

import pandas as pd
from PySide6 import QtCore, QtWidgets
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import auth
from ..settings import lib
from ..status import status


class AsyncWorker(QtCore.QThread):
    """
    Generic worker that runs a blocking function in a QThread.

    Emits:
      - resultReady(object): with the function's result on success.
      - errorOccurred(str): with an error message on failure.
    """
    resultReady = QtCore.Signal(object)
    errorOccurred = QtCore.Signal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.resultReady.emit(result)
        except Exception as ex:
            self.errorOccurred.emit(str(ex))


class SheetsFetchProgressDialog(QtWidgets.QDialog):
    """
    Generic progress dialog for asynchronous operations.

    Emits:
      - cancelled: when the user cancels the operation.
    """
    cancelled = QtCore.Signal()

    def __init__(self, timeout_seconds=180, parent=None, status_text=None):
        super().__init__(parent)
        self.timeout_seconds = timeout_seconds
        self.remaining = timeout_seconds
        self.setWindowTitle('Fetching Google Sheets Data')
        self.setModal(True)
        self.countdown_timer = QtCore.QTimer(self)
        self.countdown_timer.setInterval(1000)
        from ..ui import ui
        ui.set_stylesheet(self)
        self.status_text = status_text or "Fetching data. This could take a while, please wait..."
        self._create_ui()
        self._connect_signals()

    def showEvent(self, event):
        self.countdown_timer.start()

    def _create_ui(self):
        QtWidgets.QVBoxLayout(self)
        from ..ui import ui
        self.layout().setSpacing(ui.Size.Indicator(1.0))
        self.status_label = QtWidgets.QLabel(self.status_text)
        self.layout().addWidget(self.status_label, 1)
        self.countdown_label = QtWidgets.QLabel(f'Please wait ({self.remaining}s)...')
        self.layout().addWidget(self.countdown_label, 1)
        self.cancel_button = QtWidgets.QPushButton('Cancel')
        self.layout().addWidget(self.cancel_button, 1)

    def _connect_signals(self):
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.cancel_button.clicked.connect(self.on_cancel)

    @QtCore.Slot()
    def update_countdown(self):
        self.remaining -= 1
        self.countdown_label.setText(f'Please wait ({self.remaining}s)...')
        if self.remaining <= 0:
            self.countdown_timer.stop()
            self.countdown_label.setText('Operation timed out.')

    @QtCore.Slot()
    def on_cancel(self):
        self.cancelled.emit()
        self.reject()


def run_async_operation(func, *args, timeout_seconds=180, status_text="Fetching data.", **kwargs):
    """
    Generic asynchronous operation wrapper.

    Creates and runs an AsyncWorker with a progress dialog and event loop.

    Args:
        func: The blocking function to run.
        *args, **kwargs: Arguments passed to func.
        timeout_seconds (int): Operation timeout.
        status_text (str): Label displayed in the progress dialog.

    Returns:
        The result of the function on success.

    Raises:
        Exception: If the operation is cancelled, times out, or an error occurs.
    """
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = SheetsFetchProgressDialog(timeout_seconds=timeout_seconds, status_text=status_text)
    worker = AsyncWorker(func, *args, **kwargs)
    result = {'data': None, 'error': None}
    loop = QtCore.QEventLoop()

    worker.resultReady.connect(lambda d: (result.update({'data': d}), loop.quit()))
    worker.errorOccurred.connect(lambda err: (result.update({'error': err}), loop.quit()))
    dialog.cancelled.connect(lambda: loop.quit())

    worker.start()
    dialog.show()

    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: (dialog.countdown_timer.stop(), loop.quit()))
    timer.start(timeout_seconds * 1000)
    loop.exec()

    if worker.isRunning():
        worker.terminate()
        worker.wait()
        raise Exception("Operation cancelled or timed out.")
    dialog.close()
    if result['error']:
        raise Exception(result['error'])
    return result['data']


def get_service():
    """
    Builds and returns a Google Sheets service client.

    Returns:
        The Sheets API Resource.
    """
    creds = auth.get_creds()
    try:
        service = build('sheets', 'v4', credentials=creds)
        logging.info('Google Sheets service client created successfully.')
        return service
    except Exception as ex:
        raise status.ServiceUnavailableException from ex


def _verify_sheet_access():
    """
    (Synchronous) Verifies access to the Google Sheets API and checks if the specified spreadsheet
    exists and is accessible.

    Returns:
        The Sheets API Resource.

    Raises:
        SpreadsheetIdNotConfiguredException, ServiceUnavailableException,
        SpreadsheetWorksheetNotConfiguredException, WorksheetNotFoundException.
    """
    service = get_service()
    config = lib.settings.get_section('spreadsheet')
    spreadsheet_id = config.get('id', None)
    if not spreadsheet_id:
        raise status.SpreadsheetIdNotConfiguredException

    try:
        logging.info('Connecting to Google Sheets API...')
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        logging.info(f'Access confirmed for spreadsheet "{spreadsheet_id}".')
    except HttpError as ex:
        stat = ex.resp.status if ex.resp else None
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

    worksheet_name = config.get('worksheet', None)
    if not worksheet_name:
        raise status.SpreadsheetWorksheetNotConfiguredException

    sheet = next((s for s in result.get('sheets', [])
                  if s.get('properties', {}).get('title', '') == worksheet_name), None)
    if not sheet:
        raise status.WorksheetNotFoundException

    logging.info(f'Worksheet "{worksheet_name}" found in spreadsheet "{spreadsheet_id}".')
    return service


def _fetch_worksheet_data(service, spreadsheet_id, worksheet_name,
                          max_attempts=3, wait_seconds=2.0,
                          value_render_option='UNFORMATTED_VALUE'):
    """
    Retrieves data from a specified worksheet as a pandas DataFrame.
    The first row is assumed to be the header.

    Returns:
        A pandas DataFrame containing the worksheet data.
    """
    range_name = f'{worksheet_name}!A:Z'
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            logging.info(f'Fetching data from "{spreadsheet_id}" / "{worksheet_name}" (Attempt {attempt}).')
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueRenderOption=value_render_option,
            ).execute()
            rows = result.get('values', [])
            if not rows:
                logging.warning(f'No data found in "{worksheet_name}".')
                return pd.DataFrame()
            if len(rows) == 1:
                df = pd.DataFrame(columns=rows[0])
            else:
                df = pd.DataFrame(rows[1:], columns=rows[0])
            logging.info(f'Fetched {df.shape[0]} rows and {df.shape[1]} columns from "{worksheet_name}".')
            return df
        except HttpError as http_err:
            logging.error(f'HTTP error on attempt {attempt}/{max_attempts} for "{worksheet_name}": {http_err}')
        except (socket.timeout, ssl.SSLError, TimeoutError) as to_err:
            logging.warning(f'Timeout/SSL error on attempt {attempt}/{max_attempts} for "{worksheet_name}": {to_err}')
        except (ConnectionError, socket.gaierror, OSError) as conn_err:
            logging.warning(f'Connection error on attempt {attempt}/{max_attempts} for "{worksheet_name}": {conn_err}')
        if attempt < max_attempts:
            logging.info(f'Retrying in {wait_seconds} seconds...')
            time.sleep(wait_seconds)
        else:
            raise status.ServiceUnavailableException(
                f'All {max_attempts} attempts to fetch sheet "{worksheet_name}" have failed.'
            )
    raise status.UnknownException


def _fetch_data():
    """
    Retrieves ledger data as a pandas DataFrame using the configuration.

    Returns:
        A pandas DataFrame containing the ledger data.
    """
    config = lib.settings.get_section('spreadsheet')
    spreadsheet_id = config.get('id', None)
    if not spreadsheet_id:
        raise status.SpreadsheetIdNotConfiguredException
    worksheet_name = config.get('worksheet', None)
    if not worksheet_name:
        raise status.SpreadsheetWorksheetNotConfiguredException
    service = _verify_sheet_access()
    return _fetch_worksheet_data(service, spreadsheet_id, worksheet_name)


def _fetch_headers():
    """
    Retrieves the header row from the remote sheet's worksheet.

    Returns:
        A dict mapping header names to their declared format types.
    """
    config = lib.settings.get_section('spreadsheet')
    spreadsheet_id = config.get('id', None)
    if not spreadsheet_id:
        raise status.SpreadsheetIdNotConfiguredException
    worksheet_name = config.get('worksheet', None)
    if not worksheet_name:
        raise status.SpreadsheetWorksheetNotConfiguredException
    service = _verify_sheet_access()
    try:
        result = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=worksheet_name,
            includeGridData=True
        ).execute()
    except HttpError as ex:
        raise status.ServiceUnavailableException(f'HTTP error fetching grid data: {ex}') from ex
    except Exception as ex:
        raise status.UnknownException from ex
    sheet = next((s for s in result.get('sheets', [])
                  if s.get('properties', {}).get('title', '') == worksheet_name), None)
    if not sheet:
        raise status.WorksheetNotFoundException(f'{worksheet_name} was not found.')
    grid_data = sheet.get('data', [])
    if not grid_data or 'rowData' not in grid_data[0]:
        raise status.UnknownException(f'No grid data found for {worksheet_name}.')
    row_data = grid_data[0].get('rowData', [])
    if not row_data:
        raise status.UnknownException(f'No row data found for {worksheet_name}.')
    header_cells = row_data[0].get('values', [])
    data_cells = row_data[1].get('values', []) if len(row_data) > 1 else header_cells
    headers = {}
    for idx, header_cell in enumerate(header_cells):
        header_value = header_cell.get('formattedValue', f'Column{idx + 1}')
        cell = data_cells[idx] if idx < len(data_cells) else header_cell
        headers[header_value] = convert_types(cell)
    logging.info(f'Fetched headers for {len(headers)} columns.')
    return headers


def verify_headers():
    """
    Verify the headers of the remote spreadsheet against the local configuration.
    """
    config = lib.settings.get_section('header')
    if not config:
        raise status.HeadersInvalidException
    remote_headers = fetch_headers(timeout_seconds=180)
    if not remote_headers:
        raise status.HeadersInvalidException('No data found in the remote sheet.')
    expected_headers = set(config.keys())
    actual_headers = set(remote_headers.keys())
    mismatch = expected_headers.difference(actual_headers)
    if mismatch:
        raise status.HeadersInvalidException(
            f'Missing expected headers in remote sheet: {", ".join(mismatch)}.'
        )
    logging.info(f'Found {len(expected_headers)} headers configured correctly.')


def verify_mapping():
    """
    Verify the header mapping configuration against the remote spreadsheet's column values.

    Returns:
        A dict of remote headers for further use.
    """
    config = lib.settings.get_section('mapping')
    if not config:
        raise status.HeaderMappingInvalidException
    headers = fetch_headers(timeout_seconds=180)
    for k, v in config.items():
        if v not in headers:
            raise status.HeaderMappingInvalidException(
                f'"{v}" is not a valid header in the remote sheet.'
            )
    return headers


def _fetch_categories():
    """
    (Synchronous) Fetches a unique list of categories from the remote spreadsheet.

    Returns:
        A sorted list of unique category values.
    """
    logging.info('Fetching categories from the remote sheet...')
    verify_headers()
    headers = verify_mapping()
    config = lib.settings.get_section('mapping')
    category_column = config.get('category', None)
    if not category_column:
        raise status.HeaderMappingInvalidException('Category column not found in mapping.')
    service = _verify_sheet_access()
    spreadsheet_id = lib.settings.get_section('spreadsheet').get('id')
    worksheet_name = lib.settings.get_section('spreadsheet').get('worksheet')
    header_names = list(headers.keys())
    if category_column not in header_names:
        raise status.HeaderMappingInvalidException(f'Category "{category_column}" not found.')
    idx = header_names.index(category_column)
    column_letter = string.ascii_uppercase[idx]
    range_ = f'{worksheet_name}!{column_letter}2:{column_letter}'
    try:
        logging.info('Fetching category data from the remote sheet...')
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_
        ).execute()
    except socket.timeout as ex:
        raise status.ServiceUnavailableException(f'Timeout error fetching data: {ex}') from ex
    except HttpError as ex:
        raise status.ServiceUnavailableException(f'HTTP error fetching data: {ex}') from ex
    except Exception as ex:
        raise status.UnknownException from ex
    rows = result.get('values', [])
    if not rows:
        raise status.UnknownException('No data found in the remote sheet.')
    logging.info(f'Fetched {len(rows)} rows; parsing categories...')
    categories = sorted(set(row[0] for row in rows if row and row[0]))
    logging.info(f'Found {len(categories)} unique categories.')
    return categories


def fetch_data(timeout_seconds=180):
    """
    Asynchronously fetches ledger data as a pandas DataFrame.
    """
    return run_async_operation(_fetch_data, timeout_seconds=timeout_seconds,
                               status_text="Fetching data. This could take a while, please wait...")


def fetch_headers(timeout_seconds=180):
    """
    Asynchronously fetches the header row as a dict.
    """
    return run_async_operation(_fetch_headers, timeout_seconds=timeout_seconds,
                               status_text="Fetching headers.")


def verify_sheet_access(timeout_seconds=180):
    """
    Asynchronously verifies access to the spreadsheet, returning the Sheets API resource.
    """
    return run_async_operation(_verify_sheet_access, timeout_seconds=timeout_seconds,
                               status_text="Verifying sheet access.")


def fetch_categories(timeout_seconds=180):
    """
    Asynchronously fetches the unique list of categories.
    """
    return run_async_operation(_fetch_categories, timeout_seconds=timeout_seconds,
                               status_text="Fetching categories.")


def convert_types(cell):
    """
    Converts the source cell to a mapped type.

    Returns:
        'date' if DATE or DATE_TIME, 'int' or 'float' for numeric types, otherwise 'string'.
    """
    if not cell:
        return 'string'
    fmt_type = cell.get('userEnteredFormat', {}).get('numberFormat', {}).get('type', '')
    if fmt_type in ('DATE', 'DATE_TIME'):
        return 'date'
    if fmt_type in ('NUMBER', 'CURRENCY', 'PERCENT', 'SCIENTIFIC'):
        number_val = cell.get('effectiveValue', {}).get('numberValue')
        if number_val is not None and number_val == int(number_val):
            return 'int'
        return 'float'
    return 'string'
