"""
Local SQLite cache and data access for ledger data.

This module provides utilities to manage a local SQLite cache of Google Sheets ledger data,
including schema creation, verification, type casting, and data retrieval or updates.
It ensures the database schema, particularly the metadata table, is valid or
recreates it if necessary.
"""

import datetime
import enum
import logging
import sqlite3
import time
from typing import Any, Optional, Dict

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

# Define the expected schema for the metadata table
META_SCHEMA: Dict[str, str] = {
    'meta_id': 'INTEGER PRIMARY KEY',  # Field name and its SQL type definition part
    'last_sync': 'TEXT',
    'state': 'TEXT',
    'spreadsheet_id': 'TEXT',
    'worksheet': 'TEXT',
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
    """Return current UTC date and time as an ISO 8601 string.

    Returns:
        str: Current UTC date and time in ISO 8601 format.
    """
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def get_sql_type(column: str) -> str:
    """Get the SQLite column type for a given header column.

    Args:
        column: Configured column name from header settings.

    Returns:
        str: The SQL type as a string (e.g., 'TEXT', 'INTEGER', 'REAL').
             Defaults to 'TEXT' if the configuration type is unknown.
    """
    return TYPE_MAPPING.get(get_config_type(column), 'TEXT')


def get_config_type(column: str) -> str:
    """Get the configured data type for a column from header settings.

    Args:
        column: Column name to look up in header settings.

    Returns:
        str: Type string as defined in configuration (e.g., 'date', 'int').

    Raises:
        status.HeadersInvalidException: If the column is not found in the header configuration.
    """
    config = lib.settings.get_section('header')

    if column not in config:
        raise status.HeadersInvalidException(
            f'Column "{column}" not found in configuration. Please check the header mapping.'
        )
    return config[column]


def cast_type(column: str, value: Any) -> Any:
    """Cast a source cell value to the column type defined in the configuration.

    Provides sensible defaults or None for uncastable values.

    Args:
        column: The logical column name, used to look up its configured type.
        value: The raw value to cast.

    Returns:
        Any: The casted value, or a default (like 0, 0.0, specific date, None)
             if casting fails or value is None.
    """
    if value is None:
        return None

    config_type = get_config_type(column)  # Can raise HeadersInvalidException

    try:
        text_val = str(value)
    except (ValueError, TypeError):
        logging.debug(f'Failed to convert value "{value}" to string for column "{column}". Storing None.')
        return None

    if config_type == 'int':
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
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

    elif config_type == 'date':
        if isinstance(value, (int, float)):
            try:
                return google_serial_date_to_iso(float(value))
            except ValueError:
                logging.debug(
                    f'Failed to parse numeric value "{value}" as date for column "{column}". Storing None.')
                return None
        elif isinstance(value, str):
            try:
                if len(text_val) > 3 and ('.' in text_val or text_val.isnumeric()):  # Avoid tiny "numbers"
                    return google_serial_date_to_iso(float(text_val))
            except ValueError:
                pass

            current_loc_setting = lib.settings['locale']
            try:
                dt_obj = locale.parse_date(text_val, locale=current_loc_setting)
                return dt_obj.strftime(DATE_COLUMN_FORMAT)
            except ValueError:
                pass

            for loc_key in locale.LOCALE_MAP:
                if loc_key == current_loc_setting:
                    continue
                try:
                    dt_obj = locale.parse_date(text_val, locale=loc_key)
                    return dt_obj.strftime(DATE_COLUMN_FORMAT)
                except ValueError:
                    pass

            fallback_date = datetime.datetime(1980, 1, 1).strftime(DATE_COLUMN_FORMAT)
            logging.debug(
                f'Unable to parse "{text_val}" as a date for column "{column}". Storing {fallback_date}.'
            )
            return fallback_date

    elif config_type == 'string':
        return text_val

    logging.warning(f'Unknown config type "{config_type}" for column "{column}". Storing "{text_val}".')
    return text_val


def google_serial_date_to_iso(serial: float) -> str:
    """Converts a Google Sheets date serial to an ISO 'YYYY-MM-DD' string.

    Args:
        serial: The numeric date serial from Google Sheets.

    Returns:
        str: The date in 'YYYY-MM-DD' format.

    Raises:
        ValueError: If the serial number is out of a plausible range or conversion fails.
    """
    if serial < -20000 or serial > 2958465:
        logging.warning(f'Google date serial "{serial}" is out of plausible range.')
        raise ValueError(f'Serial date "{serial}" is out of supported range.')

    base_date = datetime.datetime(1899, 12, 30)
    try:
        day_offset = int(serial)  # Ensure it's an integer for timedelta days
        converted_date = base_date + datetime.timedelta(days=day_offset)
        return converted_date.strftime(DATE_COLUMN_FORMAT)
    except (OverflowError, ValueError) as e:
        logging.warning(f'Error converting serial date "{serial}": {e}.')
        raise ValueError(f'Invalid serial date value {serial}') from e


class DatabaseAPI(QtCore.QObject):
    """Database API for the ledger data. Handles schema creation, validation, and data access."""

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent=parent)
        self._initialize_schema_if_needed()
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect signals for cache management."""
        signals.presetAboutToBeActivated.connect(self.reset_cache)
        signals.dataFetched.connect(self.cache_data)

    def _initialize_schema_if_needed(self) -> None:
        """
        Ensures the database file and schema (especially metatable) are valid.
        If the DB file doesn't exist, or metatable is missing/invalid, it recreates them.
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = self.connection()
            db_file_exists = lib.settings.db_path.exists()

            metatable_is_valid = False
            if db_file_exists:
                if self._table_exists_in_conn(conn, Table.Meta.value):
                    cursor = conn.execute(f"PRAGMA table_info({Table.Meta.value})")
                    current_columns = {row[1] for row in cursor.fetchall()}
                    if set(META_SCHEMA.keys()).issubset(current_columns):
                        metatable_is_valid = True
                    else:
                        missing_cols = set(META_SCHEMA.keys()) - current_columns
                        logging.warning(
                            f"Metadata table '{Table.Meta.value}' schema is invalid. Missing columns: {missing_cols}. "
                            f"Schema will be recreated."
                        )
                else:
                    logging.warning(
                        f"Database file exists but metadata table '{Table.Meta.value}' is missing. "
                        f"Schema will be recreated."
                    )

            if not db_file_exists or not metatable_is_valid:
                logging.info(
                    f"Recreating database schema (DB exists: {db_file_exists}, Metatable valid: {metatable_is_valid})."
                )
                conn.execute(f"DROP TABLE IF EXISTS {Table.Meta.value}")
                conn.execute(f"DROP TABLE IF EXISTS {Table.Transactions.value}")

                meta_cols_sql = ", ".join(
                    f'"{name}" {typedef}' for name, typedef in META_SCHEMA.items()
                )
                conn.execute(f"CREATE TABLE {Table.Meta.value} ({meta_cols_sql})")

                config = lib.settings.get_section('spreadsheet')
                cfg_id = config.get('id', '')
                cfg_sheet = config.get('worksheet', '')

                conn.execute(
                    f"INSERT INTO {Table.Meta.value} (meta_id, state, last_sync, spreadsheet_id, worksheet) "
                    "VALUES (1, ?, ?, ?, ?)",  # meta_id=1, last_sync, spreadsheet_id, worksheet
                    (CacheState.Uninitialized.name, now_str(), cfg_id, cfg_sheet)
                )
                conn.commit()
                logging.info(f"Database schema including '{Table.Meta.value}' recreated successfully.")
            else:
                logging.debug("Existing database schema and metatable are considered valid.")

        except sqlite3.Error as e:
            logging.error(f"SQLite error during schema initialization: {e}. Attempting recovery.", exc_info=True)
            if conn:
                try:
                    conn.close()
                except sqlite3.Error:  # Ignore errors on close if already problematic
                    pass

            try:
                self.delete()  # Attempt to delete the problematic DB file
                self._initialize_schema_if_needed()  # Recursive call after delete
                logging.info("Database schema forcefully recreated after an error and delete.")
            except Exception as final_e:
                logging.critical(f"Failed to recover database schema even after delete: {final_e}", exc_info=True)
                raise status.CacheInvalidException(f"Unrecoverable DB schema error: {final_e}") from final_e
        finally:
            if conn:
                try:
                    conn.commit()
                    conn.close()
                except sqlite3.Error as e:
                    logging.error(f"SQLite error during final commit/close in schema init: {e}")

    @QtCore.Slot()
    def reset_cache(self) -> None:
        """Resets the local cache by deleting the database file."""
        logging.debug('Resetting local cache database.')
        try:
            DatabaseAPI.delete()
        except status.CacheInvalidException as e:
            logging.error(f"Failed to reset cache (delete DB file): {e}")

    @classmethod
    def connection(cls) -> sqlite3.Connection:
        """Return a new connection to the cache database.

        Returns:
            sqlite3.Connection: Database connection object.
        """
        db_path_str = str(lib.settings.db_path)
        lib.settings.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path_str, timeout=2.0)
        conn.set_progress_handler(lambda: logging.debug('Waiting on DB lock…'), 1000)
        return conn

    @staticmethod
    def _update_state_in_conn(conn: sqlite3.Connection, state: CacheState) -> None:
        """Update the 'state' field in the metatable using an existing connection."""
        conn.execute(f"""UPDATE {Table.Meta.value} SET state=? WHERE meta_id=1""", (state.name,))

    @classmethod
    def _table_exists_in_conn(cls, conn: sqlite3.Connection, table_name: str) -> bool:
        """Check if a table exists using an existing connection."""
        cursor = conn.execute(
            """SELECT name FROM sqlite_master WHERE type='table' AND name=?""",
            (table_name,)
        )
        return cursor.fetchone() is not None

    @classmethod
    def table_exists(cls, table_name: str) -> bool:
        """Check if a table exists in the database (opens a new connection)."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = cls.connection()
            return cls._table_exists_in_conn(conn, table_name)
        finally:
            if conn:
                conn.close()

    @classmethod
    def verify(cls) -> None:
        """
        Verify cache: DB exists, schema correct, source matches, not stale.

        Raises:
            status.CacheInvalidException: If cache is invalid for various reasons.
            status.HeadersInvalidException: If configured headers mismatch cache.
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = cls.connection()

            if not lib.settings.db_path.exists():
                raise status.CacheInvalidException(
                    f'Local cache DB missing at {lib.settings.db_path} post-initialization.'
                )

            if not cls._table_exists_in_conn(conn, Table.Meta.value):
                try:
                    cls._update_state_in_conn(conn, CacheState.Error)
                    conn.commit()
                except sqlite3.Error:  # Best effort if table doesn't exist
                    pass
                raise status.CacheInvalidException(
                    f"Metadata table '{Table.Meta.value}' missing. Critical error."
                )

            # Attempt to read metadata; catch missing columns in older schemas
            try:
                meta_row = conn.execute(
                    f"SELECT spreadsheet_id, worksheet, last_sync FROM {Table.Meta.value} WHERE meta_id=1"
                ).fetchone()
            except sqlite3.OperationalError as e:
                logging.warning(
                    "Metadata table schema outdated or missing columns: %s", e
                )
                # Invalidate cache; prompt schema reset
                raise status.CacheInvalidException(
                    'Cache schema outdated (missing metadata columns); please reset the cache.'
                ) from e
            if not meta_row:
                try:
                    conn.execute(f"INSERT OR REPLACE INTO {Table.Meta.value} (meta_id, state) VALUES (1, ?)",
                                 (CacheState.Error.name,))
                    conn.commit()
                except sqlite3.Error:  # Best effort
                    pass
                raise status.CacheInvalidException(f"Metadata entry (meta_id=1) missing in '{Table.Meta.value}'.")

            db_id, db_sheet, last_sync_raw = meta_row
            config = lib.settings.get_section('spreadsheet')
            cfg_id = config.get('id', '')
            cfg_sheet = config.get('worksheet', '')

            if db_id != cfg_id or db_sheet != cfg_sheet:
                logging.warning(
                    f'DB source mismatch. DB: (id={db_id}, sheet={db_sheet}), '
                    f'Config: (id={cfg_id}, sheet={cfg_sheet}). Marking Stale.'
                )
                cls._update_state_in_conn(conn, CacheState.Stale)
                conn.commit()
                raise status.CacheInvalidException(
                    f'DB source (ID: "{db_id}", Sheet: "{db_sheet}") '
                    f'differs from config (ID: "{cfg_id}", Sheet: "{cfg_sheet}").'
                )

            if not cls._table_exists_in_conn(conn, Table.Transactions.value):
                cls._update_state_in_conn(conn, CacheState.Uninitialized)
                conn.commit()
                raise status.CacheInvalidException(
                    f"Table '{Table.Transactions.value}' not found. Cache uninitialized."
                )

            cursor = conn.execute(f"PRAGMA table_info({Table.Transactions.value})")
            cached_columns = {row[1] for row in cursor.fetchall() if row[1] != 'local_id'}

            cfg_header_cols = set(lib.settings.get_section('header').keys())
            if not cfg_header_cols:
                cls._update_state_in_conn(conn, CacheState.Stale)
                conn.commit()
                raise status.HeadersInvalidException(
                    'No headers configured. Cannot verify cache. Sync required.'
                )

            if cached_columns != cfg_header_cols:
                diff = cached_columns.symmetric_difference(cfg_header_cols)
                cls._update_state_in_conn(conn, CacheState.Stale)
                conn.commit()
                raise status.CacheInvalidException(
                    f"Cache column schema mismatch. Difference: {diff}. Sync required."
                )

            if not last_sync_raw:
                cls._update_state_in_conn(conn, CacheState.Stale)
                conn.commit()
                raise status.CacheInvalidException('Cache stale: last sync date not recorded.')
            try:
                last_sync_dt = datetime.datetime.fromisoformat(last_sync_raw)
            except ValueError:
                cls._update_state_in_conn(conn, CacheState.Stale)
                conn.commit()
                raise status.CacheInvalidException(f'Cache stale: invalid last sync date format ({last_sync_raw}).')

            if (datetime.datetime.now(datetime.timezone.utc) - last_sync_dt).days >= CACHE_MAX_AGE_DAYS:
                cls._update_state_in_conn(conn, CacheState.Stale)
                conn.commit()
                raise status.CacheInvalidException(f'Cache stale. Last sync: {last_sync_dt}.')

            count_row = conn.execute(f"SELECT COUNT(*) FROM {Table.Transactions.value}").fetchone()
            if count_row and count_row[0] == 0:
                cls._update_state_in_conn(conn, CacheState.Empty)
                conn.commit()
                return

            cls._update_state_in_conn(conn, CacheState.Valid)
            conn.commit()
            logging.debug(
                f"Cache valid: last_sync={last_sync_dt}, rows={count_row[0] if count_row else 'N/A'}"
            )

        except sqlite3.Error as e:
            logging.error(f"SQLite error during cache verification: {e}", exc_info=True)
            if conn:
                try:
                    cls._update_state_in_conn(conn, CacheState.Error)
                    conn.commit()
                except sqlite3.Error:  # Best effort
                    pass
            raise status.CacheInvalidException(f"SQLite error verifying cache: {e}") from e
        finally:
            if conn:
                conn.close()

    @classmethod
    def delete(cls) -> None:
        """Delete the local cache database file, retrying on failure.

        Raises:
            status.CacheInvalidException: If unable to remove the database file after retries.
        """
        db_file = lib.settings.db_path
        if not db_file.exists():
            logging.debug('No cache database found to delete.')
            return

        max_attempts = 5
        attempt = 0
        wait_seconds = 1.0

        while attempt < max_attempts:
            attempt += 1
            try:
                db_file.unlink()
                logging.info(f'Cache database removed: {db_file}')
                return
            except OSError as ex:
                logging.error(f'Error removing cache DB (attempt {attempt}/{max_attempts}): {ex}')
                if attempt < max_attempts:
                    logging.debug(f'Retrying in {wait_seconds} seconds...')
                    time.sleep(wait_seconds)
                    wait_seconds *= 1.5
                else:
                    raise status.CacheInvalidException(
                        f'Failed to remove cache DB {db_file} after {max_attempts} attempts: {ex}'
                    ) from ex
            except Exception as ex:
                logging.error(f'Unexpected error removing cache DB (attempt {attempt}/{max_attempts}): {ex}',
                              exc_info=True)
                raise status.CacheInvalidException(
                    f'Unexpected error removing cache DB {db_file}: {ex}'
                ) from ex

    @classmethod
    def stamp(cls) -> None:
        """Update the last sync timestamp and source identifiers in the metadata table."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = cls.connection()
            config = lib.settings.get_section('spreadsheet')
            spreadsheet_id = config.get('id', '')
            worksheet = config.get('worksheet', '')
            conn.execute(
                f"UPDATE {Table.Meta.value} SET last_sync=?, spreadsheet_id=?, worksheet=? WHERE meta_id=1",
                (now_str(), spreadsheet_id, worksheet)
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

    def get_stamp(self) -> Optional[datetime.datetime]:
        """Retrieve the last synchronization timestamp.

        Returns:
            Optional[datetime.datetime]: Last sync datetime object, or None if not set/invalid.
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = self.connection()
            if not self._table_exists_in_conn(conn, Table.Meta.value):
                logging.warning(f"Metatable '{Table.Meta.value}' not found when getting stamp.")
                return None

            cursor = conn.execute(f"SELECT last_sync FROM {Table.Meta.value} WHERE meta_id=1")
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    return datetime.datetime.fromisoformat(row[0])
                except ValueError:
                    logging.warning(f'Invalid last sync date format in DB: {row[0]}.')
            return None
        finally:
            if conn:
                conn.close()

    @classmethod
    def set_state(cls, state: CacheState) -> None:
        """Update the cache state in the metadata table.

        Args:
            state: New cache state to set.
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = cls.connection()
            if cls._table_exists_in_conn(conn, Table.Meta.value):
                cls._update_state_in_conn(conn, state)
                conn.commit()
                logging.debug(f'Cache state updated to: {state.value}.')
            else:
                logging.error(f"Metatable '{Table.Meta.value}' not found when setting state. State not set.")
        finally:
            if conn:
                conn.close()

    @classmethod
    def get_state(cls) -> CacheState:
        """Retrieve the current cache state from the metadata table.

        Returns:
            CacheState: Current state, or CacheState.Error if unable to determine.
        """
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = cls.connection()
            if not cls._table_exists_in_conn(conn, Table.Meta.value):
                logging.warning(f"Metatable '{Table.Meta.value}' not found when getting state.")
                return CacheState.Error

            cursor = conn.execute(f"SELECT state FROM {Table.Meta.value} WHERE meta_id=1")
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    return CacheState[row[0]]
                except KeyError:
                    logging.warning(f"Invalid state value '{row[0]}' found in database.")
                    return CacheState.Error
            logging.warning("No state found in metatable or meta_id=1 row missing.")
            return CacheState.Error
        finally:
            if conn:
                conn.close()

    @classmethod
    def data(cls) -> pd.DataFrame:
        """Load cached transactions into a pandas DataFrame after verification.

        Returns:
            pandas.DataFrame: Transactions DataFrame. Empty if cache is invalid,
                              stale, empty, uninitialized, or in error state.
        """
        try:
            cls.verify()
        except (status.CacheInvalidException, status.HeadersInvalidException) as e:
            logging.warning(f'Cache verification failed, returning empty DataFrame: {e}')
            return pd.DataFrame()

        current_state = cls.get_state()
        if current_state == CacheState.Valid:
            conn: Optional[sqlite3.Connection] = None
            try:
                conn = cls.connection()
                if not cls._table_exists_in_conn(conn, Table.Transactions.value):
                    logging.error(f"Table '{Table.Transactions.value}' missing despite state '{current_state}'.")
                    cls.set_state(CacheState.Error)
                    return pd.DataFrame()

                df = pd.read_sql_query(f"SELECT * FROM {Table.Transactions.value}", conn)
                logging.debug(f'Loaded {len(df)} rows from "{Table.Transactions.value}".')
                return df
            except sqlite3.Error as e:
                logging.error(f'Error loading data from DB: {e}', exc_info=True)
                cls.set_state(CacheState.Error)
                return pd.DataFrame()
            finally:
                if conn:
                    conn.close()
        elif current_state == CacheState.Empty:
            logging.info('Cache is valid but empty. Returning empty DataFrame.')
            return pd.DataFrame()
        else:
            logging.warning(f'Cache state is "{current_state.value}" post-verification. Returning empty DataFrame.')
            return pd.DataFrame()

    @classmethod
    def get_row(cls, local_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a transaction row by its local_id.

        Args:
            local_id: Primary key ('local_id') of the transaction.

        Returns:
            Optional[Dict[str, Any]]: Row data as a dictionary, or None if not found.
        """
        logging.debug(f'Fetching row with local_id={local_id}')
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = cls.connection()
            if not cls._table_exists_in_conn(conn, Table.Transactions.value):
                logging.warning(f"Table '{Table.Transactions.value}' not found when getting row.")
                return None

            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                f"SELECT * FROM {Table.Transactions.value} WHERE local_id = ?", (local_id,)
            )
            row = cursor.fetchone()
            if not row:
                logging.warning(f'No row found for local_id={local_id}')
                return None

            result = dict(row)
            logging.debug(f'Retrieved row for local_id={local_id}: {result}')
            return result
        finally:
            if conn:
                conn.close()

    @classmethod
    def update_cell(cls, local_id: int, column: str, new_value: Any) -> None:
        """Update a specific cell in the transactions table.

        Args:
            local_id: Primary key ('local_id') of the row.
            column: Actual database column name to update.
            new_value: New value to assign to the cell.

        Raises:
            sqlite3.Error: If the update operation fails.
        """
        logging.debug(f'Updating cell: local_id={local_id}, column="{column}", new_value="{new_value}"')
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = cls.connection()
            if not cls._table_exists_in_conn(conn, Table.Transactions.value):
                logging.error(f"Table '{Table.Transactions.value}' not found for update. Update failed.")
                raise sqlite3.OperationalError(f"Table {Table.Transactions.value} not found.")

            conn.execute(
                f'UPDATE "{Table.Transactions.value}" SET "{column}" = ? WHERE local_id = ?',
                (new_value, local_id)
            )
            conn.commit()
            logging.info(f'Cell updated for local_id={local_id}, column="{column}".')
        except sqlite3.Error as e:
            logging.error(f'Failed to update cell for local_id={local_id}, column="{column}": {e}', exc_info=True)
            if conn: conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    @classmethod
    def cache_data(cls, df: pd.DataFrame) -> None:
        """Cache a DataFrame of ledger data into the local database.

        Replaces existing transactions table data.

        Args:
            df: pandas.DataFrame containing transactions to cache.

        Raises:
            status.HeadersInvalidException: If DataFrame columns mismatch configuration.
            sqlite3.Error: For database-related issues during caching.
        """
        conn: Optional[sqlite3.Connection] = None
        logging.debug(f'Starting data caching for {len(df)} rows.')
        try:
            conn = cls.connection()
            if not cls._table_exists_in_conn(conn, Table.Meta.value):
                logging.error(f"Metatable '{Table.Meta.value}' missing. Cannot cache data.")
                raise sqlite3.OperationalError(f"Metatable '{Table.Meta.value}' missing.")

            conn.execute(f"DROP TABLE IF EXISTS {Table.Transactions.value}")
            logging.debug(f'Dropped existing table: "{Table.Transactions.value}".')

            cfg_header = lib.settings.get_section('header')
            if not cfg_header:
                cls.set_state(CacheState.Error)  # No headers, cannot proceed.
                cls.stamp()
                raise status.HeadersInvalidException("Cannot cache data: No headers configured.")

            config_column_names = list(cfg_header.keys())

            if df.empty:
                empty_cols_sql = ['"local_id" INTEGER PRIMARY KEY AUTOINCREMENT'] + \
                                 [f'"{col_name}" {get_sql_type(col_name)}' for col_name in config_column_names]
                conn.execute(f"CREATE TABLE {Table.Transactions.value} ({','.join(empty_cols_sql)})")
                conn.commit()
                cls.set_state(CacheState.Empty)
                cls.stamp()
                logging.info('DataFrame is empty. Cached an empty transactions table.')
                return

            df_columns = df.columns.tolist()
            if set(df_columns) != set(config_column_names):
                diff = set(df_columns).symmetric_difference(set(config_column_names))
                cls.set_state(CacheState.Stale)
                cls.stamp()
                raise status.HeadersInvalidException(
                    f'DataFrame columns differ from configured headers. Difference: {diff}.\n'
                    f'DataFrame: {df_columns}\nConfig: {config_column_names}'
                )

            logging.debug(f'DataFrame columns match configuration: {df_columns}')
            table_cols_sql = ['"local_id" INTEGER PRIMARY KEY AUTOINCREMENT'] + \
                             [f'"{col_name}" {get_sql_type(col_name)}' for col_name in config_column_names]
            conn.execute(f"CREATE TABLE {Table.Transactions.value} ({','.join(table_cols_sql)})")
            logging.debug(f'Created new table "{Table.Transactions.value}".')

            df_reordered = df[config_column_names]

            rows_to_insert = []
            for i, row_tuple in enumerate(df_reordered.itertuples(index=False, name=None)):
                current_col_name_for_error = ""  # For more specific error logging
                try:
                    casted_row_values = []
                    for col_idx, col_name in enumerate(config_column_names):
                        current_col_name_for_error = col_name
                        casted_row_values.append(cast_type(col_name, row_tuple[col_idx]))
                    rows_to_insert.append(casted_row_values)
                except status.HeadersInvalidException as hie:
                    logging.error(f"Error casting data for row {i} due to header config: {hie}")
                    cls.set_state(CacheState.Error)
                    cls.stamp()
                    raise
                except Exception as e_cast:
                    logging.error(
                        f"Unexpected error casting data for row {i}, col '{current_col_name_for_error}': {e_cast}",
                        exc_info=True)
                    raise sqlite3.DataError(
                        f"Data casting failed for row {i}, column '{current_col_name_for_error}'") from e_cast

            sql_placeholders = ','.join(['?'] * len(config_column_names))
            sql_column_names_part = ','.join([f'"{col}"' for col in config_column_names])
            insert_sql = (
                f'INSERT INTO "{Table.Transactions.value}" ({sql_column_names_part}) '
                f'VALUES ({sql_placeholders})'
            )

            conn.executemany(insert_sql, rows_to_insert)
            conn.commit()

            logging.info(f'Successfully cached {len(rows_to_insert)} rows into "{Table.Transactions.value}".')
            cls.set_state(CacheState.Valid)
            cls.stamp()

        except sqlite3.Error as e:
            logging.error(f'SQLite error during data caching: {e}', exc_info=True)
            if conn: conn.rollback()
            try:
                cls.set_state(CacheState.Error)
            except Exception:  # Best effort
                pass
            raise
        except status.HeadersInvalidException:
            if conn: conn.rollback()
            # State already set before raising in the block above
            raise
        except Exception as e:
            logging.error(f'Unexpected error during data caching: {e}', exc_info=True)
            if conn: conn.rollback()
            try:
                cls.set_state(CacheState.Error)
            except Exception:  # Best effort
                pass
            raise sqlite3.DatabaseError(f"Generic error during caching: {e}") from e
        finally:
            if conn:
                conn.close()


database = DatabaseAPI()
