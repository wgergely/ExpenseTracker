"""
Local Cache Database Module

This module maintains a local SQLite cache of remote ledger data from Google Sheets.

The primary functions are:
  - cache_remote_data: Fetches remote data from Google Sheets and caches it locally to the database.
  - get_cached_data: Returns the cached data as a pandas DataFrame.
  - verify_db: Verifies that the local cache database is valid and up-to-date.
"""

import datetime
import logging
import sqlite3
import time
from typing import Optional, Dict, Any

import pandas as pd
from googleapiclient.errors import HttpError

from ..auth import service
from ..settings import lib

logging.basicConfig(level=logging.INFO)

TABLE_TRANSACTIONS = 'transactions'
TABLE_META = 'cache_meta'
CACHE_MAX_AGE_DAYS = 7

DATE_LOCALES = {
    'en_GB': '%d/%m/%Y',
    'de_DE': '%d.%m.%Y',
    'en_US': '%m/%d/%Y',
    'hu_HU': '%Y.%m.%d',
    'jp_JP': '%Y/%m/%d',
}

DATABASE_DATE_FORMAT = '%Y-%m-%d'


def verify_db() -> None:
    """Checks whether the local cache database is present and valid."""
    if not lib.settings.db_path.exists():
        logging.error('No local cache DB path found.')
        raise RuntimeError('No local cache DB path found.')

    try:
        with sqlite3.connect(str(lib.settings.db_path)) as conn:
            if not table_exists(conn, TABLE_TRANSACTIONS):
                logging.error('The "transactions" table is missing.')
                raise RuntimeError('The "transactions" table is missing.')

            state = get_cache_state(conn)
            if not state['is_valid']:
                logging.warning('Cache is marked invalid.')

            if is_stale(state['last_sync']):
                logging.warning('Cache is older than the allowed threshold and will be invalidated.')
                invalidate_cache(reason='Cache is older than 7 days')

        logging.info('The cache is valid.')

    except sqlite3.Error as ex:
        logging.error(f'Error while verifying the local DB: {ex}')
        raise RuntimeError(f'Error while verifying the local DB: {ex}') from ex


def create_db() -> None:
    """Creates or replaces the local cache database."""
    if lib.settings.db_path.exists():
        logging.info(f'{lib.settings.db_path} already exists, removing it...')
        lib.settings.db_path.unlink()

    with sqlite3.connect(str(lib.settings.db_path)) as conn:
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


def cache_remote_data(force: bool = False) -> None:
    """Fetches remote ledger data from Google Sheets and caches it locally."""
    if not lib.settings.db_path.exists():
        logging.info('No local DB found. A new one will be created.')
        create_db()

    header_data = lib.settings.get_section('header')
    if not header_data:
        raise RuntimeError('No header data found in the configuration. Cannot proceed.')

    logging.info('Fetching remote data...')
    try:
        data = service.fetch_data()
    except (RuntimeError, HttpError) as ex:
        invalidate_cache(reason=f'Remote data pull failed: {ex}')
        raise RuntimeError(f'Failed to fetch remote data. Reason: {ex}') from ex

    try:
        validate_dataframe(data, header_data=header_data)
    except RuntimeError as ex:
        invalidate_cache(reason=f'Validation failed: {ex}')
        raise RuntimeError(f'Failed to validate remote data. Reason: {ex}') from ex

    try:
        with sqlite3.connect(str(lib.settings.db_path)) as conn:
            recreate_transactions_table(conn, data, header_data)
            insert_data(conn, data, header_data)
            update_meta_valid(conn)
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
    try:
        verify_db()
    except RuntimeError as ex:
        logging.error(f'Local cache DB is invalid: {ex}')
        return pd.DataFrame()

    if force:
        logging.info('Forcing a reload of the remote data.')
        cache_remote_data(force=force)

    conn = None
    try:
        conn = sqlite3.connect(str(lib.settings.db_path))
        df = pd.read_sql_query('SELECT * FROM transactions', conn)
        logging.info(f'Loaded {len(df)} rows from the "transactions" table.')
        return df
    except sqlite3.Error as ex:
        logging.error(f'Error reading from local DB: {ex}')
    finally:
        if conn is not None:
            conn.close()

    return pd.DataFrame()


def clear_local_cache() -> bool:
    """Removes the local DB file from the system.

    Returns:
        True if the DB file was successfully removed, False otherwise.
    """
    if not lib.settings.db_path.exists():
        logging.info('No local DB file found to clear.')
        return True

    try:
        with sqlite3.connect(str(lib.settings.db_path)) as conn:
            pass
    except sqlite3.Error as ex:
        logging.error(f'Error closing the local DB connection: {ex}')
        return False

    time.sleep(0.5)

    try:
        lib.settings.db_path.unlink()
    except OSError as ex:
        logging.error(f'Error removing the local DB file: {ex}')
        return False

    logging.info('The local DB file was removed.')
    return True


def invalidate_cache(reason: str) -> None:
    """Marks the cache as invalid."""
    if not lib.settings.db_path.exists():
        return

    with sqlite3.connect(str(lib.settings.db_path)) as conn:
        if table_exists(conn, TABLE_META):
            conn.execute(f"""
                UPDATE {TABLE_META}
                SET is_valid=0,
                    error_message=?
                WHERE meta_id=1
            """, (reason,))
    logging.warning(f'The cache was marked invalid. Reason: {reason}')


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Determines if table_name exists in the connected SQLite database."""
    cursor = conn.execute(
        """SELECT name FROM sqlite_master WHERE type='table' AND name=?""",
        (table_name,)
    )
    return cursor.fetchone() is not None


def get_cache_state(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Reads the meta table to determine if the cache is valid, when it was last synced,
    and any stored error messages.
    """
    state = {'last_sync': None, 'is_valid': False, 'error_message': None}
    if not table_exists(conn, TABLE_META):
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


def update_meta_valid(conn: sqlite3.Connection) -> None:
    """Marks the cache as valid, clears any previous error message,
    and sets last_sync to the current UTC time.
    """
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(f"""
        UPDATE {TABLE_META}
        SET is_valid=1,
            error_message=NULL,
            last_sync=?
        WHERE meta_id=1
    """, (now_str,))


def is_stale(last_sync: Optional[datetime.datetime]) -> bool:
    """
    Returns True if last_sync is missing or older than CACHE_MAX_AGE_DAYS.
    """
    if not last_sync:
        return True
    age = datetime.datetime.now(datetime.timezone.utc) - last_sync
    return age.days >= CACHE_MAX_AGE_DAYS


def validate_dataframe(data: pd.DataFrame, header_data: Dict[str, str]) -> None:
    """Validates that the remote dataset is non-empty and has the expected columns."""
    if data.empty or data.shape[0] < 1:
        raise RuntimeError('Remote dataset is empty or missing a header row.')

    remote_columns = set(str(col) for col in data.columns)
    expected = set(header_data.keys())
    missing = expected - remote_columns
    extra = remote_columns - expected

    if missing or extra:
        error_msg = (
            f'Column mismatch in remote data. '
            f'Expected columns: {sorted(expected)}; '
            f'Found columns: {sorted(remote_columns)}; '
            f'Missing: {sorted(missing)}; '
            f'Unexpected: {sorted(extra)}'
        )
        logging.error(error_msg)
        raise RuntimeError(error_msg)


def recreate_transactions_table(
        conn: sqlite3.Connection,
        data: pd.DataFrame,
        header_data: Dict[str, str]
) -> None:
    """Drops the existing transactions table (if any) and creates a new one based on the data headers."""
    conn.execute(f'DROP TABLE IF EXISTS {TABLE_TRANSACTIONS}')
    headers = [str(col) for col in data.columns]
    defs_list = ['"local_id" INTEGER PRIMARY KEY AUTOINCREMENT']

    for header in headers:
        col_name_raw = _sanitize_column_name(header)
        col_type = get_sqlite_type(header, header_data)
        col_name_escaped = col_name_raw.replace('"', '""')
        defs_list.append(f'"{col_name_escaped}" {col_type}')
    create_sql = f'CREATE TABLE "{TABLE_TRANSACTIONS}" (\n  {",".join(defs_list)}\n)'
    conn.execute(create_sql)


def insert_data(
        conn: sqlite3.Connection,
        data: pd.DataFrame,
        header_data: Dict[str, str]
) -> None:
    """
    Inserts rows from 'data' into the transactions table, performing necessary type conversion.
    """
    headers = [str(col) for col in data.columns]
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
    # For performance, consider using executemany if the dataset grows large.
    for row in rows:
        converted = [convert_value(h, val, header_data) for h, val in zip(headers, row)]
        conn.execute(insert_stmt, converted)


def _sanitize_column_name(header: str) -> str:
    """
    Returns a sanitized column name, converting 'id' to 'remote_id'.
    """
    if header.lower() == 'id':
        return 'remote_id'
    return header


def get_sqlite_type(header: str, header_data: Dict[str, str]) -> str:
    """
    Determines the appropriate SQLite type for 'header' using the ledger.json type map.
    """
    declared_type = header_data.get(header, 'string')
    if declared_type == 'int':
        return 'INTEGER'
    elif declared_type == 'float':
        return 'REAL'
    elif declared_type == 'date':
        return 'TEXT'
    elif declared_type == 'string':
        return 'TEXT'
    return 'TEXT'


def convert_value(header: str, value: Any, header_data: Dict[str, str]) -> Any:
    """
    Converts 'value' to an appropriate Python type based on the ledger.json config.
    """
    if value is None:
        return None

    try:
        text_val = str(value)
    except:
        logging.warning(f'Failed to convert value "{value}" to string for column "{header}". Storing None')
        return None

    declared_type = header_data.get(header, 'string')

    if declared_type == 'int':
        if isinstance(value, (bool, int)):
            return value

        if text_val == '':
            return 0

        try:
            return int(text_val)
        except ValueError:
            logging.warning(f'Failed to parse "{text_val}" as integer for column "{header}". Storing 0.')
            return 0

    elif declared_type == 'float':
        if isinstance(value, float):
            return value

        if text_val == '':
            return 0.0

        try:
            return float(text_val)
        except ValueError:
            logging.warning(f'Failed to parse "{text_val}" as float for column "{header}". Storing 0.0.')
            return 0.0

    if declared_type == 'date':
        if isinstance(value, (int, float)):
            try:
                return google_serial_date_to_iso(float(value))
            except ValueError:
                logging.warning(f'Failed to parse "{value}" as date for column "{header}". Storing None.')
                return None
        elif isinstance(value, str):
            try:
                return google_serial_date_to_iso(float(text_val))
            except:
                pass

            # Try to parse the date string by guessing the locale of the date format
            for locale, fmt in DATE_LOCALES.items():
                try:
                    dt = datetime.datetime.strptime(text_val, fmt)
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    continue

            logging.warning(f'Unable to parse "{text_val}" as a date for column "{header}". Storing None')
    elif declared_type == 'string':
        if isinstance(value, str):
            return value

        try:
            return text_val
        except ValueError:
            logging.warning(f'Failed to convert "{value}" to string for column "{header}". Storing None')

    return None


def google_serial_date_to_iso(serial: float) -> str:
    """Converts a Google Sheets date serial to an ISO 'YYYY-MM-DD' string.

    """
    base_date = datetime.datetime(1899, 12, 30)
    day_offset = int(serial)

    if day_offset < -10000:
        logging.warning(f'Serial date "{serial}" is suspiciously negative. Storing blank.')
        return ''

    converted_date = base_date + datetime.timedelta(days=day_offset)
    return converted_date.strftime(DATABASE_DATE_FORMAT)
