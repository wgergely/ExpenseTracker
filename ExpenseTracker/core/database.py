"""
Local Cache Database Module

This module maintains a local SQLite cache of remote ledger data from Google Sheets.
The primary functions are:
  - fetch_data: Fetches remote data and caches it locally.
  - get_cached_data: Returns cached data as a pandas DataFrame.
  - verify: Verifies that the local cache is valid and up-to-date.
"""

import datetime
import enum
import logging
import sqlite3
import time
from typing import Any, Optional

import pandas as pd
from PySide6 import QtCore

from ..settings import lib
from ..settings import locale
from ..status import status
from ..ui.actions import signals

CACHE_MAX_AGE_DAYS = 7
DATE_COLUMN_FORMAT = '%Y-%m-%d'

TYPE_MAPPING = {
    'date': 'TEXT',
    'int': 'INTEGER',
    'float': 'REAL',
    'string': 'TEXT',
}


class Table(enum.StrEnum):
    """Enum for database tables."""
    Meta = 'metatable'
    Transactions = 'transactions'


class CacheState(enum.StrEnum):
    """Enum for cache state values."""
    Uninitialized = 'cache is uninitialized'
    Empty = 'cache is empty'
    Stale = 'cache is stale'
    Error = 'cache has error'
    Valid = 'cache is valid'


def now_str() -> str:
    """Return current UTC date and time as an ISO 8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def get_sql_type(column: str) -> str:
    return TYPE_MAPPING.get(get_config_type(column), 'TEXT')


def get_config_type(column: str) -> str:
    config = lib.settings.get_section('header')

    if column not in config:
        raise status.HeadersInvalidException(
            f'Column "{column}" not found in configuration. Please check the header mapping.'
        )

    return config[column]


def cast_type(column: str, value: Any) -> Any:
    """Cast a source cell value to the column type defined in the configuration.

    """
    if value is None:
        return None

    config_type = get_config_type(column)

    try:
        text_val = str(value)
    except (ValueError, TypeError):
        logging.debug(f'Failed to convert value "{value}" to string for column "{column}". Storing None')
        return None

    if config_type == 'int':
        if isinstance(value, (bool, int)):
            return value

        if text_val == '':
            return 0

        try:
            return int(text_val)
        except ValueError:
            logging.debug(f'Failed to parse "{text_val}" as integer for column "{column}". Storing 0.')
            return 0

    elif config_type == 'float':
        if isinstance(value, float):
            return value

        if text_val == '':
            return 0.0

        try:
            return float(text_val)
        except ValueError:
            logging.debug(f'Failed to parse "{text_val}" as float for column "{column}". Storing 0.0.')
            return 0.0

    if config_type == 'date':
        if isinstance(value, (int, float)):
            try:
                return google_serial_date_to_iso(float(value))
            except ValueError:
                logging.debug(f'Failed to parse "{value}" as date for column "{column}". Storing None.')
                return None
        elif isinstance(value, str):
            # assuming an int-like string could be read as a date serial
            try:
                return google_serial_date_to_iso(float(text_val))
            except:
                pass

            # Carry on to the guesswork...
            # Try to parse the date string by guessing the locale of the date format

            # Start with the current locale
            current_loc = lib.settings['locale']
            try:
                dt = locale.parse_date(text_val, locale=current_loc)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass

            for loc in locale.LOCALE_MAP:
                try:
                    dt = locale.parse_date(text_val, locale=loc)
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    pass

            dt = datetime.datetime(1980, 1, 1)
            logging.debug(
                f'Unable to parse "{text_val}" as a date for column "{column}". Storing {dt.strftime("%Y-%m-%d")}')
            return dt.strftime('%Y-%m-%d')

    elif config_type == 'string':
        if isinstance(value, str):
            return value

        try:
            return text_val
        except ValueError:
            logging.debug(f'Failed to convert "{value}" to string for column "{column}". Storing None')

    logging.debug(f'Unknown config type "{config_type}" for column "{column}". Storing None.')
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
    return converted_date.strftime(DATE_COLUMN_FORMAT)


class DatabaseAPI(QtCore.QObject):
    """Database API for the ledger data."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.create()

        self._connect_signals()

    def _connect_signals(self):
        signals.dataFetched.connect(self.cache_data)

    @classmethod
    def connection(cls) -> sqlite3.Connection:
        """Return a new SQLite database connection."""

        return sqlite3.connect(str(lib.settings.db_path))

    @classmethod
    def table_exists(cls, table_name: str) -> bool:
        """Return True if table_name exists in the database."""
        conn = cls.connection()
        try:
            cursor = conn.execute(
                """SELECT name FROM sqlite_master WHERE type='table' AND name=?""",
                (table_name,)
            )
            return cursor.fetchone() is not None
        finally:
            conn.commit()
            conn.close()

    @classmethod
    def verify(cls) -> None:
        """Verify that the local cache database exists and is valid."""

        conn = cls.connection()
        if not lib.settings.db_path.exists():
            raise status.CacheInvalidException(
                f'Could not create the local cache database at {lib.settings.db_path}'
            )

        try:
            if not cls.table_exists(Table.Transactions):
                conn.commit()
                cls.set_state(CacheState.Uninitialized)
                raise status.CacheInvalidException(
                    'Database uninitialized. No transactions table found.'
                )

            cursor = conn.execute(f"""SELECT * FROM {Table.Transactions} LIMIT 1""")
            columns = [col[0] for col in cursor.description]
            if 'local_id' in columns:
                columns.remove('local_id')
            logging.info(f'Cached transactions with {len(columns)} columns: {columns}')
            config = lib.settings.get_section('header')
            if not config:
                conn.commit()
                cls.set_state(CacheState.Stale)
                raise status.HeadersInvalidException(
                    'No header data found in configuration, data needs sync.'
                )

            difference = set(columns).symmetric_difference(set(config.keys()))
            if difference:
                logging.info(f'Columns differ between config and cache: {difference}')
                conn.commit()
                cls.set_state(CacheState.Stale)
                raise status.CacheInvalidException(f'Column mismatch: {difference}')

            cursor = conn.execute(f"""SELECT last_sync FROM {Table.Meta} WHERE meta_id=1""")
            row = cursor.fetchone()
            if row and not row[0]:
                conn.commit()
                cls.set_state(CacheState.Stale)
                raise status.CacheInvalidException('Cache is stale. Last sync date not found.')

            try:
                last_sync = datetime.datetime.fromisoformat(row[0])
            except ValueError:
                logging.warning(f'Invalid last sync date format: {row[0]}. Defaulting to 1980-01-01.')
                last_sync = datetime.datetime(1980, 1, 1)

            if row and row[0]:
                age = datetime.datetime.now(datetime.timezone.utc) - last_sync
                if age.days >= CACHE_MAX_AGE_DAYS:
                    conn.commit()
                    cls.set_state(CacheState.Stale)
                    raise status.CacheInvalidException(f'Cache is stale. Last sync: {last_sync}')

            cursor = conn.execute(f"""SELECT COUNT(*) FROM {Table.Transactions}""")
            row = cursor.fetchone()
            if row and row[0] == 0:
                logging.info('Cache is empty. No transactions found.')
                conn.commit()
                cls.set_state(CacheState.Empty)
                return

            conn.commit()
            cls.set_state(CacheState.Valid)
            logging.info(
                f'Cache is valid. Last sync={last_sync}, Rows={row[0]}, Columns={len(columns)}'
            )
        finally:
            conn.commit()
            conn.close()

    @classmethod
    def create(cls) -> None:
        """Create a new local cache database."""

        if lib.settings.db_path.exists():
            logging.warning('Cache database already exists. Ignoring create request.')
            return

        conn = cls.connection()

        try:
            logging.debug(f'Creating cache database at {lib.settings.db_path}')
            conn.execute(f"""
                CREATE TABLE {Table.Meta} (
                    meta_id INTEGER PRIMARY KEY,
                    last_sync TEXT,
                    state TEXT
                )
            """)

            conn.execute(f"""
                INSERT INTO {Table.Meta} (meta_id, state, last_sync)
                VALUES (1, ?, ?)
            """, (CacheState.Uninitialized, now_str()))
        finally:
            conn.commit()
            conn.close()

    @classmethod
    def delete(cls) -> None:
        """Delete the local cache database ensuring the connection is properly closed."""

        if not lib.settings.db_path.exists():
            logging.info('No cache database found to delete.')
            return

        max_attempts = 5
        attempt = 0
        wait_seconds = 1.0

        while attempt < max_attempts:
            attempt += 1
            if not lib.settings.db_path.exists():
                logging.info('Cache database file already removed.')
                break
            try:
                lib.settings.db_path.unlink()
                logging.info(f'Cache database removed: {lib.settings.db_path}')
                break
            except Exception as ex:
                logging.error(f'Error removing cache database (attempt {attempt}): {ex}')
                if attempt < max_attempts:
                    logging.info(f'Retrying in {wait_seconds} seconds...')
                    time.sleep(wait_seconds)
        else:
            raise status.CacheInvalidException(
                f'Failed to remove cache database after {max_attempts} attempts.'
            )

    @classmethod
    def stamp(cls) -> None:
        """Update the last sync time in the database."""
        conn = cls.connection()
        try:
            conn.execute(f"""
                UPDATE {Table.Meta}
                SET last_sync=?
                WHERE meta_id=1
            """, (now_str(),))
        finally:
            conn.commit()
            conn.close()

    def get_stamp(self) -> Optional[datetime.datetime]:
        """Get the last sync time from the database."""
        conn = self.connection()
        try:
            cursor = conn.execute(f"""
                SELECT last_sync
                FROM {Table.Meta}
                WHERE meta_id=1
            """)
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    return datetime.datetime.fromisoformat(row[0])
                except ValueError:
                    logging.warning(f'Invalid last sync date format: {row[0]}. Defaulting to None.')
            return None
        finally:
            conn.commit()
            conn.close()

    @classmethod
    def set_state(cls, state: CacheState) -> None:
        """Mark the cache state."""
        if state not in CacheState:
            raise ValueError(f'Invalidation reason must be one of {list(CacheState)}')

        conn = cls.connection()
        try:
            if cls.table_exists(Table.Meta):
                conn.execute(f"UPDATE {Table.Meta} SET state=? WHERE meta_id=1", (state.name,))
            logging.info(f'State updated: {state}.')
        finally:
            conn.commit()
            conn.close()

    @classmethod
    def get_state(cls) -> CacheState:
        """Get the current state of the cache."""
        conn = cls.connection()
        try:
            cursor = conn.execute(f"""
                SELECT state
                FROM {Table.Meta}
                WHERE meta_id=1
            """)
            row = cursor.fetchone()
            if row and row[0]:
                return next((f for f in CacheState if f.name == row[0]), CacheState.Error)
            return CacheState.Error
        finally:
            conn.commit()
            conn.close()

    @classmethod
    def data(cls) -> pd.DataFrame:
        """
        Loads the cached data from disk as a DataFrame.

        Returns:
            A DataFrame with all columns from the transaction table, or an empty DataFrame if the
            database is invalid or an error occurs during loading.

        """
        try:
            cls.verify()
        except status.CacheInvalidException:
            return pd.DataFrame()

        state = cls.get_state()
        if state == CacheState.Empty:
            logging.warning(f'Cache is empty. No transactions found.')
            return pd.DataFrame()
        elif state == CacheState.Stale:
            logging.warning(f'Cache is stale. Data needs to be synced.')
            return pd.DataFrame()
        elif state == CacheState.Error:
            logging.warning(f'Cache has error. Data needs to be synced.')
            return pd.DataFrame()
        elif state == CacheState.Uninitialized:
            logging.warning(f'Cache is uninitialized. Data needs to be synced.')
            return pd.DataFrame()

        conn = cls.connection()
        try:
            df = pd.read_sql_query("""SELECT * FROM transactions""", conn)
            logging.info(f'Loaded {len(df)} rows from the "transactions" table.')
            return df
        except (Exception,) as e:
            logging.error(f'Error loading data from the database: {e}')
            return pd.DataFrame()
        finally:
            conn.commit()
            conn.close()

    @classmethod
    def cache_data(cls, df: pd.DataFrame) -> None:
        conn = cls.connection()

        logging.info(f'Caching data.')
        try:
            conn.execute(f"""DROP TABLE IF EXISTS {Table.Transactions}""")
            logging.info(f'Dropped the transactions table: {Table.Transactions}')

            if df.empty:
                conn.commit()
                cls.set_state(CacheState.Empty)
                cls.stamp()
                logging.warning('DataFrame is empty. No data to cache.')
                return

            # Get the column names from the DataFrame
            logging.info(f'Checking columns...')
            df_columns = df.columns.tolist()

            config = lib.settings.get_section('header')
            cf_columns = list(config.keys())

            difference = set(df_columns).symmetric_difference(set(cf_columns))
            if difference:
                cls.set_state(CacheState.Stale)
                cls.stamp()
                raise status.HeadersInvalidException(f'Columns differ between config and cache: {difference}')
            else:
                logging.info(f'Columns match: {df_columns}')

            # Create the table
            logging.info(f'Creating transactions table: {Table.Transactions}')

            cols_sql = [f'"{col}" {get_sql_type(col)}' for col in df_columns]
            cols_sql.insert(0, '"local_id" INTEGER PRIMARY KEY AUTOINCREMENT')
            conn.execute(f"""
                CREATE TABLE {Table.Transactions} (
                    {",".join(cols_sql)}
                )
            """)

            # Insert the data
            logging.info(f'Inserting data into transactions table: {Table.Transactions}')

            rows = list(df.itertuples(index=False, name=None))
            placeholders = ','.join(['?'] * len(df_columns))

            _columns = [f'"{col}"' for col in df_columns]
            sql = (
                f'INSERT INTO "{Table.Transactions}" '
                f'({",".join(_columns)}) '
                f'VALUES ({placeholders})'
            )

            logging.debug(f'Inserting {len(rows)} rows into the "{Table.Transactions}" table.')
            values = [[cast_type(h, val) for h, val in zip(df_columns, row)] for row in rows]
            conn.executemany(sql, values)
            conn.commit()

            logging.info(f'Cached {len(rows)} rows into the "{Table.Transactions}" table.')
            cls.set_state(CacheState.Valid)
            cls.stamp()
        finally:
            conn.commit()
            conn.close()


database = DatabaseAPI()
