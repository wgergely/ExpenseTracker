# ExpensesTracker/lib/google/service.py
"""
Google Sheets Service Module.

Provides functions to load ledger configuration, authenticate with Google Sheets,
and retrieve a specified worksheet as a NumPy array.
"""

import os
import json
import logging
import socket
import ssl
import time

import numpy as np
from typing import Dict, Any, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import auth

logging.basicConfig(level=logging.INFO)

LEDGER_CONFIG_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    '..',
    'config',
    'ledger.json'
))

def load_ledger_config(path: Optional[str] = None) -> Dict[str, str]:
    """
    Loads the ledger configuration from a JSON file containing:
    {
      "id": "<spreadsheet_id>",
      "sheet": "<worksheet_name>"
    }

    Args:
        path: Optional path to the ledger.json file.

    Returns:
        A dictionary with 'id' (spreadsheet ID) and 'sheet' (worksheet name).

    Raises:
        RuntimeError: If the file is missing, malformed, or lacks required fields.

    """

    if path is None:
        path = LEDGER_CONFIG_PATH

    if not os.path.exists(path):
        raise RuntimeError(
            f'No ledger.json file found at {path}. This file must contain '
            'at least the "id" (spreadsheet ID) and "sheet" (worksheet name).'
        )

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as ex:
        raise RuntimeError(
            f'Invalid JSON in {path}. Error details: {ex}'
        ) from ex

    if not isinstance(data, dict):
        raise RuntimeError('Expected a JSON object in ledger.json.')

    if not data.get('id'):
        raise RuntimeError('The "id" field is missing or empty in ledger.json.')
    if not data.get('sheet'):
        raise RuntimeError('The "sheet" field is missing or empty in ledger.json.')

    return {
        'id': str(data['id']).strip(),
        'sheet': str(data['sheet']).strip()
    }


def create_sheets_service(force: bool = False):
    """
    Builds and returns a Google Sheets service client.

    Args:
        force: If True, forces new OAuth credentials instead of using cached credentials.

    Returns:
        A Sheets API service client (googleapiclient.discovery.Resource).

    """

    creds = auth.authenticate(force=force)
    return build('sheets', 'v4', credentials=creds)


def verify_sheet_access(service, spreadsheet_id: str) -> None:
    """
    Verifies that the authenticated user can access the specified spreadsheet.

    Args:
        service: The Sheets API service client.
        spreadsheet_id: The unique ID of the target spreadsheet.

    Raises:
        RuntimeError: If the spreadsheet cannot be found or access is denied.

    """

    try:
        service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        logging.info(f'Access confirmed for spreadsheet "{spreadsheet_id}".')
    except HttpError as ex:
        status = ex.resp.status if ex.resp else None
        if status == 404:
            raise RuntimeError(
                f'Spreadsheet "{spreadsheet_id}" not found (HTTP 404).'
            ) from ex
        elif status == 403:
            raise RuntimeError(
                f'Access denied (HTTP 403) for spreadsheet "{spreadsheet_id}". '
                'Please share the sheet with your authenticated Google account.'
            ) from ex
        else:
            raise RuntimeError(
                f'Error accessing spreadsheet "{spreadsheet_id}": {ex}'
            ) from ex


def fetch_sheet(
    service,
    spreadsheet_id: str,
    worksheet_name: str,
    max_attempts: int = 3,
    wait_seconds: float = 2.0
) -> np.ndarray:
    """
    Retrieves data from a specified worksheet as a NumPy array, retrying on network
    and timeout errors. Returns numeric columns as unformatted floats rather than
    strings with currency symbols.
    """
    import logging, time, socket, ssl
    import numpy as np
    from googleapiclient.errors import HttpError

    range_name = f'{worksheet_name}!A:Z'
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueRenderOption='UNFORMATTED_VALUE'  # <--- KEY ARGUMENT
            ).execute()

            rows = result.get('values', [])
            if not rows:
                logging.warning(
                    f'No data found in "{worksheet_name}". Returning an empty array.'
                )
                return np.array([], dtype=object)

            data_array = np.array(rows, dtype=object)
            logging.info(
                f'Fetched {data_array.shape[0]} rows and {data_array.shape[1]} columns '
                f'from "{worksheet_name}" on attempt {attempt} of {max_attempts} '
                f'using UNFORMATTED_VALUE.'
            )
            return data_array

        except HttpError as http_err:
            msg = (
                f'HTTP error fetching sheet "{worksheet_name}" (attempt {attempt} of {max_attempts}). '
                f'Error details: {http_err}'
            )
            logging.error(msg)
            raise RuntimeError(msg) from http_err

        except (socket.timeout, ssl.SSLError, TimeoutError) as to_err:
            msg = (
                f'Timeout or SSL error on attempt {attempt} of {max_attempts} while fetching '
                f'sheet "{worksheet_name}". Details: {to_err}'
            )
            logging.warning(msg)

        except (ConnectionError, socket.gaierror, OSError) as conn_err:
            msg = (
                f'Connection error on attempt {attempt} of {max_attempts} while fetching '
                f'sheet "{worksheet_name}". Details: {conn_err}'
            )
            logging.warning(msg)

        if attempt < max_attempts:
            logging.info(f'Retrying in {wait_seconds} seconds...')
            time.sleep(wait_seconds)
        else:
            raise RuntimeError(
                f'All {max_attempts} attempts to fetch sheet "{worksheet_name}" have failed. '
                'Check your network connection, spreadsheet permissions, or try again later.'
            )


def get_ledger_data(force: bool = False) -> np.ndarray:
    """
    Retrieves ledger data as a NumPy array using the configuration in ledger.json.

    This function loads ledger.json to get the spreadsheet ID and worksheet name,
    authenticates the user, optionally, forcing re-auth, verifies read access,
    and fetches the data as a 2D NumPy array.

    Args:
        force: If True, forces new OAuth credentials.

    Returns:
        A 2D NumPy array containing the ledger data.

    Raises:
        RuntimeError: If ledger.json is missing or invalid, credentials can't be obtained,
            or access to the spreadsheet is denied.

    """

    config = load_ledger_config()
    spreadsheet_id = config['id']
    worksheet_name = config['sheet']

    service = create_sheets_service(force=force)
    verify_sheet_access(service, spreadsheet_id)
    return fetch_sheet(service, spreadsheet_id, worksheet_name)
