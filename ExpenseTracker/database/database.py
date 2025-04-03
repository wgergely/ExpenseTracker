"""
Local Cache Database Module

This module maintains a local SQLite cache of remote ledger data from Google Sheets.
The cache is stored at ${temp}/ExpenseTracker/datacache.db. It can invalidate data
after a certain age and mark itself invalid if the remote data can't be fetched or
validated. Column types are defined in ledger.json.

The two primary functions in this module are:
  - get_remote_data: Fetches remote data from Google Sheets and caches it locally.
  - get_cached_data: Returns the cached data as a pandas DataFrame.
  - verify_db: Verifies that the local cache database is valid and up-to-date.

Examples:
    >>> if verify_db():
    ...     print("Local cache is valid.")
    ... else:
    ...     get_remote_data()

    >>> df = get_cached_data()

"""

import datetime
import functools
import json
import logging
import os
import pathlib
import sqlite3
import tempfile
from typing import Optional, Dict, Any

import pandas as pd
from googleapiclient.errors import HttpError

from ..auth import service

logging.basicConfig(level=logging.INFO)

DB_DIR = pathlib.Path(tempfile.gettempdir()) / 'ExpenseTracker'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'datacache.db'
LEDGER_CONFIG_PATH = pathlib.Path(os.path.dirname(__file__)).parent / 'config' / 'ledger.json'

TABLE_TRANSACTIONS = 'transactions'
TABLE_META = 'cache_meta'
CACHE_MAX_AGE_DAYS = 7

@functools.lru_cache(maxsize=1)
def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Loads and validates the ledger.json file, which must contain at least:
      {
        "id": "<spreadsheet_id>",
        "sheet": "<worksheet_name>",
        "header": { "ID": "int", ... }
      }
    Raises RuntimeError if the file is missing, cannot be parsed, or lacks required fields.
    """
    if path is None:
        path = str(LEDGER_CONFIG_PATH)
    if not os.path.exists(path):
        raise RuntimeError(
            f"No ledger.json file found at {path}. The file must define "
            '"id", "sheet", and "header" keys.'
        )
    try:
        with open(path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except (json.JSONDecodeError, OSError) as ex:
        raise RuntimeError(f"Unable to load ledger config from {path}: {ex}") from ex
    if not isinstance(config_data, dict):
        raise RuntimeError(f"Expected a JSON object in {path}, but got something else.")
    if 'id' not in config_data or not config_data['id']:
        raise RuntimeError("ledger.json is missing a valid 'id' field.")
    if 'sheet' not in config_data or not config_data['sheet']:
        raise RuntimeError("ledger.json is missing a valid 'sheet' field.")
    if 'header' not in config_data or not isinstance(config_data['header'], dict):
        raise RuntimeError("ledger.json must contain a 'header' object with column definitions.")
    return config_data


def verify_db() -> bool:
    """
    Checks whether the local cache database is present and valid.
    A valid cache must have the necessary tables, not be marked invalid,
    and not be older than CACHE_MAX_AGE_DAYS.
    """
    if not DB_PATH.exists():
        logging.info('No local cache DB found.')
        return False

    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            if not _table_exists(conn, TABLE_TRANSACTIONS):
                logging.info('The "transactions" table is missing.')
                return False
            state = _get_cache_state(conn)
            if not state['is_valid']:
                logging.info('Cache is marked invalid.')
                return False
            if _is_stale(state['last_sync']):
                logging.info('Cache is older than the allowed threshold and will be invalidated.')
                invalidate_cache(reason='Cache is older than 7 days')
                return False
            logging.info('Local cache database is present, valid, and not stale.')
            return True

    except sqlite3.Error as ex:
        logging.warning(f'Error while verifying the local DB: {ex}')
        return False


def create_db() -> None:
    """
    Creates or replaces the local cache database. Initializes a meta table to
    track cache validity, last sync time, and error details.
    """
    if DB_PATH.exists():
        logging.info('Deleting the existing DB file to create a new one.')
        DB_PATH.unlink()
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute(f"""
            CREATE TABLE {TABLE_META}(
                meta_id INTEGER PRIMARY KEY,
                last_sync TEXT,
                is_valid INTEGER,
                error_message TEXT
            )
        """)
        conn.execute(f"""
            INSERT INTO {TABLE_META}(meta_id, last_sync, is_valid, error_message)
            VALUES(1, NULL, 0, 'Initialized with no data yet.')
        """)
    logging.info('A new local cache DB was created with an empty meta table.')


def get_remote_data(force: bool = False) -> None:
    """
    Fetches remote ledger data from Google Sheets, validates it against the column
    definitions in ledger.json, and stores it in the local cache. If data retrieval
    or validation fails, the cache is marked invalid.
    """
    if not DB_PATH.exists():
        logging.info('No local DB found. A new one will be created.')
        create_db()
    try:
        ledger_config = load_config()
        column_type_map = _parse_config_types(ledger_config['header'])
        data = service.get_data(force=force)
        _validate_dataframe(data, expected_columns=set(column_type_map.keys()))
        with sqlite3.connect(str(DB_PATH)) as conn:
            _recreate_transactions_table(conn, data, column_type_map)
            _insert_data(conn, data, column_type_map)
            _update_meta_valid(conn)
        logging.info('Remote data was fetched and cached successfully.')
    except (RuntimeError, HttpError) as ex:
        invalidate_cache(reason=f'Remote data pull failed: {ex}')
        raise RuntimeError(f'Failed to fetch or store remote data. Reason: {ex}') from ex


def get_cached_data(force: bool = False) -> pd.DataFrame:
    """
    Loads all rows from the 'transactions' table in the local cache database into a pandas DataFrame.

    Args:
        force: If True, forces a reload of the data from the remote source.
               If False, checks if the local cache is valid before loading.

    Returns:
        A DataFrame with all columns from the transaction table, or an empty DataFrame if the
        database is invalid or an error occurs during loading.
    """
    if not verify_db():
        logging.warning('Local cache DB is invalid or missing. Returning an empty DataFrame.')
        return pd.DataFrame()

    if force:
        logging.info('Forcing a reload of the remote data.')
        get_remote_data(force=force)

    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        df = pd.read_sql_query('SELECT * FROM transactions', conn)
    except sqlite3.Error as ex:
        logging.error(f'Error reading from local DB: {ex}')
        return pd.DataFrame()
    finally:
        if 'conn' in locals() and conn:
            conn.close()

    logging.info(f'Loaded {len(df)} rows from the "transactions" table.')
    return df


def clear_local_cache() -> None:
    """
    Removes the entire local DB file from the system.
    """
    if not DB_PATH.exists():
        logging.info('No local DB file found to clear.')
        return True

    # Ensure the DB file is not in use before deleting and close all connections before unlinking
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.close()
    except sqlite3.Error as ex:
        logging.error(f'Error closing the local DB connection: {ex}')
        return False

    try:
        DB_PATH.unlink()
    except OSError as ex:
        logging.error(f'Error removing the local DB file: {ex}')
        return False

    logging.info('The local DB file was removed.')
    return True



def invalidate_cache(reason: str) -> None:
    """
    Marks the cache as invalid by updating the meta table.
    """
    if not DB_PATH.exists():
        return

    with sqlite3.connect(str(DB_PATH)) as conn:
        if _table_exists(conn, TABLE_META):
            conn.execute(f"""
                UPDATE {TABLE_META}
                SET is_valid=0,
                    error_message=?
                WHERE meta_id=1
            """, (reason,))
    logging.warning(f'The cache was marked invalid. Reason: {reason}')


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """
    Determines if table_name exists in the connected SQLite database.
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def _get_cache_state(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Reads the meta table to determine if the cache is valid, when it was last synced,
    and any stored error messages.
    """
    state = {'last_sync': None, 'is_valid': False, 'error_message': None}
    if not _table_exists(conn, TABLE_META):
        return state
    row = conn.execute(f"""
        SELECT last_sync, is_valid, error_message
        FROM {TABLE_META}
        WHERE meta_id=1
    """).fetchone()
    if not row:
        return state
    last_sync_str, valid_flag, err_msg = row
    if last_sync_str:
        state['last_sync'] = datetime.datetime.fromisoformat(last_sync_str)
    state['is_valid'] = bool(valid_flag)
    state['error_message'] = err_msg
    return state


def _update_meta_valid(conn: sqlite3.Connection) -> None:
    """
    Marks the cache as valid, clears any previous error message,
    and sets last_sync to the current UTC time.
    """
    now_str = datetime.datetime.utcnow().isoformat()
    conn.execute(f"""
        UPDATE {TABLE_META}
        SET is_valid=1,
            error_message=NULL,
            last_sync=?
        WHERE meta_id=1
    """, (now_str,))


def _is_stale(last_sync: Optional[datetime.datetime]) -> bool:
    """
    Returns True if last_sync is missing or older than CACHE_MAX_AGE_DAYS.
    """
    if not last_sync:
        return True
    age = datetime.datetime.utcnow() - last_sync
    return age.days >= CACHE_MAX_AGE_DAYS


def _validate_dataframe(data: pd.DataFrame, expected_columns: set) -> None:
    """
    Checks that 'data' has at least a header row and contains all expected columns.
    If there is a discrepancy, logs a clear error message detailing the expected columns,
    the columns found in the remote data, and lists the missing and unexpected columns.
    """
    if data.empty or data.shape[0] < 1:
        raise RuntimeError('Remote dataset is empty or missing a header row.')
    remote_columns = set(str(col).lower().strip() for col in data.columns)
    expected = set(col.lower().strip() for col in expected_columns)
    missing = expected - remote_columns
    extra = remote_columns - expected
    if missing or extra:
        error_msg = (
            f"Column mismatch in remote data. "
            f"Expected columns: {sorted(expected)}; "
            f"Found columns: {sorted(remote_columns)}; "
            f"Missing: {sorted(missing)}; "
            f"Unexpected: {sorted(extra)}"
        )
        logging.error(error_msg)
        raise RuntimeError(error_msg)


def _recreate_transactions_table(
        conn: sqlite3.Connection,
        data: pd.DataFrame,
        column_type_map: Dict[str, str]
) -> None:
    """
    Drops the existing transactions table if present, then creates a new one based on
    the headers in 'data' and the ledger.json type map.
    """
    conn.execute(f'DROP TABLE IF EXISTS {TABLE_TRANSACTIONS}')
    headers = [str(col).strip() for col in data.columns]
    defs_list = ['"local_id" INTEGER PRIMARY KEY AUTOINCREMENT']
    for header in headers:
        col_name_raw = _sanitize_column_name(header)
        col_type = _infer_sqlite_type(header, column_type_map)
        col_name_escaped = col_name_raw.replace('"', '""')
        defs_list.append(f'"{col_name_escaped}" {col_type}')
    create_sql = f'CREATE TABLE "{TABLE_TRANSACTIONS}" (\n  {",".join(defs_list)}\n)'
    conn.execute(create_sql)


def _insert_data(
        conn: sqlite3.Connection,
        data: pd.DataFrame,
        column_type_map: Dict[str, str]
) -> None:
    """
    Inserts rows from 'data' into the transactions table, performing necessary type conversion.
    """
    headers = [str(col).strip() for col in data.columns]
    rows = list(data.itertuples(index=False, name=None))
    col_names = []
    for h in headers:
        raw_name = _sanitize_column_name(h)
        escaped = raw_name.replace('"', '""')
        col_names.append(f'"{escaped}"')
    placeholders = ','.join(['?'] * len(col_names))
    insert_stmt = (
        f'INSERT INTO "{TABLE_TRANSACTIONS}" '
        f'({",".join(col_names)}) '
        f'VALUES ({placeholders})'
    )
    logging.info(f'Inserting {len(rows)} rows into the "{TABLE_TRANSACTIONS}" table.')
    for row in rows:
        converted = [_convert_value(h, val, column_type_map) for h, val in zip(headers, row)]
        conn.execute(insert_stmt, converted)


def _sanitize_column_name(header: str) -> str:
    """
    Returns a sanitized column name, converting 'id' to 'remote_id'.
    """
    if header.lower() == 'id':
        return 'remote_id'
    return header


def _infer_sqlite_type(raw_header: str, type_map: Dict[str, str]) -> str:
    """
    Determines the appropriate SQLite type for 'raw_header' using the ledger.json type map.
    """
    declared_type = _get_declared_type(raw_header, type_map)
    if declared_type == 'int':
        return 'INTEGER'
    elif declared_type == 'float':
        return 'REAL'
    elif declared_type == 'date':
        return 'TEXT'
    elif declared_type == 'string':
        return 'TEXT'
    return 'TEXT'


def _convert_value(raw_header: str, value: Any, type_map: Dict[str, str]) -> Any:
    """
    Converts 'value' to an appropriate Python type based on the ledger.json config.
      - For 'int': Converts empty strings to 0 and invalid values to None.
      - For 'float': Strips currency symbols and converts empty strings to 0.0.
      - For 'date': If the value is numeric, converts it as a Google Sheets serial.
        Otherwise, attempts to parse the date in either ISO ('%Y-%m-%d') or UK ('%d/%m/%Y') format.
      - Otherwise: Treats the value as text.
    """
    if value is None:
        return None
    text_val = str(value).strip()
    declared_type = _get_declared_type(raw_header, type_map)
    if declared_type == 'int':
        if text_val == '':
            return 0
        try:
            return int(text_val)
        except ValueError:
            logging.warning(f'Failed to parse "{text_val}" as integer for column "{raw_header}". Storing None.')
            return None
    if declared_type == 'float':
        if text_val == '':
            return 0.0
        text_val = text_val.replace(',', '').replace('£', '').replace('$', '').replace('€', '')
        try:
            return float(text_val)
        except ValueError:
            logging.warning(f'Failed to parse "{text_val}" as float for column "{raw_header}". Storing None.')
            return None
    if declared_type == 'date':
        if text_val == '':
            return ''
        try:
            serial_float = float(text_val)
            return _google_serial_date_to_iso(serial_float)
        except ValueError:
            pass
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                dt = datetime.datetime.strptime(text_val, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        logging.warning(f'Unable to parse "{text_val}" as a date for column "{raw_header}". Storing raw.')
        return text_val
    return text_val


def _google_serial_date_to_iso(serial: float) -> str:
    """
    Converts a Google Sheets date serial to an ISO 'YYYY-MM-DD' string.
    """
    base_date = datetime.datetime(1899, 12, 30)
    day_offset = int(serial)
    if day_offset < -10000:
        logging.warning(f'Serial date "{serial}" is suspiciously negative. Storing blank.')
        return ''
    converted_date = base_date + datetime.timedelta(days=day_offset)
    return converted_date.strftime('%Y-%m-%d')


def _parse_config_types(header_config: Dict[str, str]) -> Dict[str, str]:
    """
    Produces a dictionary mapping each column name to its declared type based on the ledger.json config.
    """
    parsed = {}
    for col_name, col_type in header_config.items():
        parsed[col_name.lower().strip()] = col_type.lower().strip()
    return parsed


def _get_declared_type(raw_header: str, type_map: Dict[str, str]) -> str:
    """
    Returns the declared type from the ledger.json config for the specified header.
    Defaults to 'string' if nothing is declared.
    """
    lower_header = raw_header.lower().strip()
    if lower_header in type_map:
        return type_map[lower_header]
    return 'string'
