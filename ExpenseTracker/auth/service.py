"""
Google Sheets Service Module.

Provides functions to load ledger configuration, authenticate with Google Sheets,
and retrieve the specified worksheet as a pandas DataFrame.
"""

import logging
import socket
import ssl
import time

import pandas as pd
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from . import auth
from ..settings import lib

logging.basicConfig(level=logging.INFO)


def get_service() -> Resource:
    """
    Builds and returns a Google Sheets service client.

    Returns:
        A Sheets API service client.
    """
    creds = auth.authenticate(force=not auth.verify_creds())
    return build('sheets', 'v4', credentials=creds)


def verify_sheet_access(service) -> None:
    """
    Verifies that the authenticated user can access the specified spreadsheet.

    Args:
        service: The Sheets API service client.

    Raises:
        RuntimeError: If the spreadsheet cannot be found or access is denied.
        ValueError: If the spreadsheet ID or worksheet name is not found in the configuration.

    """

    spreadsheet_config = lib.settings.get_section('spreadsheet')
    if 'id' not in spreadsheet_config:
        raise ValueError('Spreadsheet ID not found in configuration.')

    if 'worksheet' not in spreadsheet_config:
        raise ValueError('Worksheet name not found in configuration.')

    spreadsheet_id = spreadsheet_config.get('id', '')
    if not spreadsheet_id:
        raise ValueError('Spreadsheet ID is empty in configuration.')

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


def _fetch_data(
        service,
        spreadsheet_id: str,
        worksheet_name: str,
        max_attempts: int = 3,
        wait_seconds: float = 2.0
) -> pd.DataFrame:
    """
    Retrieves data from a specified worksheet as a pandas DataFrame.
    The first row is assumed to be the header.

    Args:
        service: The Sheets API service client.
        spreadsheet_id: The unique ID of the spreadsheet.
        worksheet_name: The name of the worksheet.
        max_attempts: Maximum number of fetch attempts.
        wait_seconds: Seconds to wait between retries.

    Returns:
        A pandas DataFrame containing the worksheet data.
    """
    range_name = f'{worksheet_name}!A:Z'
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueRenderOption='UNFORMATTED_VALUE'
            ).execute()

            rows = result.get('values', [])
            if not rows:
                logging.warning(
                    f'No data found in "{worksheet_name}". Returning an empty DataFrame.'
                )
                return pd.DataFrame()

            # Assume the first row contains headers.
            if len(rows) == 1:
                df = pd.DataFrame(columns=rows[0])
            else:
                df = pd.DataFrame(rows[1:], columns=rows[0])
            logging.info(
                f'Fetched {df.shape[0]} rows and {df.shape[1]} columns from "{worksheet_name}" '
                f'on attempt {attempt} of {max_attempts} using UNFORMATTED_VALUE.'
            )
            return df

        except HttpError as http_err:
            msg = (
                f'HTTP error fetching sheet "{worksheet_name}" (attempt {attempt} of {max_attempts}). '
                f'Error details: {http_err}'
            )
            logging.error(msg)
        except (socket.timeout, ssl.SSLError, TimeoutError) as to_err:
            logging.warning(
                f'Timeout or SSL error on attempt {attempt} of {max_attempts} while fetching '
                f'sheet "{worksheet_name}". Details: {to_err}'
            )
        except (ConnectionError, socket.gaierror, OSError) as conn_err:
            logging.warning(
                f'Connection error on attempt {attempt} of {max_attempts} while fetching '
                f'sheet "{worksheet_name}". Details: {conn_err}'
            )

        if attempt < max_attempts:
            logging.info(f'Retrying in {wait_seconds} seconds...')
            time.sleep(wait_seconds)
        else:
            logging.warning(
                f'All {max_attempts} attempts to fetch sheet "{worksheet_name}" have failed. '
                'Check your network connection, spreadsheet permissions, or try again later.'
            )

    return pd.DataFrame()


def fetch_data() -> pd.DataFrame:
    """
    Retrieves ledger data as a pandas DataFrame using the configuration in ledger.json.

    Returns:
        A pandas DataFrame containing the ledger data.
    """
    from ..settings import lib

    spreadsheet_config = lib.settings.get_section('spreadsheet')

    spreadsheet_id = spreadsheet_config.get('id', '')
    if not spreadsheet_id:
        logging.error('Could not fetch data, spreadsheet ID is empty.')
        return pd.DataFrame()

    worksheet_name = spreadsheet_config.get('worksheet', '')
    if not worksheet_name:
        logging.error('Could not fetch data, worksheet name is empty.')
        return pd.DataFrame()

    try:
        service = get_service()
    except RuntimeError as ex:
        logging.error(f'Could not fetch data, failed to create Google Sheets API service: {ex}')
        return pd.DataFrame()

    try:
        verify_sheet_access(service)
    except RuntimeError as ex:
        logging.error(f'Could not fetch data, failed to verify sheet access: {ex}')
        return pd.DataFrame()
    except ValueError as ex:
        logging.error(f'Could not fetch data, missing configuration: {ex}')
        return pd.DataFrame()

    return _fetch_data(service, spreadsheet_id, worksheet_name)
