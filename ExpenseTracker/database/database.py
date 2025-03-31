"""
Local Cache Database Module

This module maintains a local SQLite cache of remote ledger data from Google Sheets.
The cache is stored at ${temp}/ExpensesTracker/datacache.db. It can invalidate data
after a certain age and mark itself invalid if the remote data can't be fetched or
validated. You can create a new cache, verify it, fetch data from Google Sheets, clear
the existing data, or mark the cache as invalid. Column types are defined in ledger.json.
"""

import datetime
import json
import logging
import os
import pathlib
import sqlite3
import tempfile
from typing import Optional, Dict, Any

import numpy as np
from googleapiclient.errors import HttpError

# If you have a separate module for pulling actual data from Google Sheets,
# you can import it here. For example:
from ..auth import service

logging.basicConfig(level=logging.INFO)

# Directory and file paths for the local database and ledger configuration.
DB_DIR = pathlib.Path(tempfile.gettempdir()) / 'ExpensesTracker'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / 'datacache.db'

LEDGER_CONFIG_PATH = pathlib.Path(os.path.dirname(__file__)).parent / 'config' / 'ledger.json'

# Names of SQLite tables used for caching.
TABLE_TRANSACTIONS = 'transactions'
TABLE_META = 'cache_meta'

# Basic column requirements for the sheet data, ignoring case.
REQUIRED_COLUMNS = {'id', 'date', '€€€'}

# Maximum age of cache data (in days) before it is considered stale.
CACHE_MAX_AGE_DAYS = 7


class LocalCacheManager:
    """
    This class manages a local SQLite database that stores remote ledger data.
    It supports creating and verifying the database, reading ledger.json for
    column definitions, fetching new data from Google Sheets, clearing the cache,
    and marking the cache as invalid if data retrieval or validation fails.
    """

    @classmethod
    def load_ledger_config(cls, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Loads and validates the ledger.json file, which must contain at least:
          {
            "id": "<spreadsheet_id>",
            "sheet": "<worksheet_name>",
            "header": {
                "ID": "int",
                ...
            }
          }

        If fields are missing or the file is invalid, an exception is raised.
        Returns a dict containing "id", "sheet", and "header".

        Args:
            path: Optional path to the ledger.json file. Defaults to LEDGER_CONFIG_PATH.

        Returns:
            A dictionary with keys: "id", "sheet", and "header".

        Raises:
            RuntimeError if the file is missing, cannot be parsed, or lacks required fields.
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
            raise RuntimeError(f"ledger.json is missing a valid 'id' field.")

        if 'sheet' not in config_data or not config_data['sheet']:
            raise RuntimeError(f"ledger.json is missing a valid 'sheet' field.")

        if 'header' not in config_data or not isinstance(config_data['header'], dict):
            raise RuntimeError(f"ledger.json must contain a 'header' object with column definitions.")

        return config_data

    @classmethod
    def verify_db(cls) -> bool:
        """
        Checks whether the local cache database is present and valid. A valid cache must
        have the necessary tables, must not be explicitly marked invalid, and must not be
        older than the maximum allowed age. Returns False if any of these conditions fail.
        """
        if not DB_PATH.exists():
            logging.info('No local cache DB found.')
            return False

        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                if not cls._table_exists(conn, TABLE_TRANSACTIONS):
                    logging.info('The "transactions" table is missing.')
                    return False

                state = cls._get_cache_state(conn)
                if not state['is_valid']:
                    logging.info('Cache is marked invalid.')
                    return False

                if cls._is_stale(state['last_sync']):
                    logging.info('Cache is older than the allowed threshold and will be invalidated.')
                    cls.invalidate_cache(reason='Cache is older than 7 days')
                    return False

                logging.info('Local cache database is present, valid, and not stale.')
                return True
        except sqlite3.Error as ex:
            logging.warning(f'Error while verifying the local DB: {ex}')
            return False

    @classmethod
    def create_db(cls) -> None:
        """
        Creates or replaces the local cache database. A meta table is initialized to
        track whether the cache is valid, when data was last synced, and error details.
        The transactions table is not created until data is actually pulled.
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

    @classmethod
    def pull_remote_data(cls, force: bool = False) -> None:
        """
        Fetches remote ledger data from Google Sheets, validates it against the required
        columns, and stores it in the local cache. The ledger.json file is also loaded here
        to determine column types. If the cache DB doesn't exist, a new one is created.
        If data retrieval or validation fails, the cache is marked invalid.

        Args:
            force: If True, forces re-authentication when contacting Google.

        Raises:
            RuntimeError if fetching or storing the data fails.
        """
        if not DB_PATH.exists():
            logging.info('No local DB found. A new one will be created.')
            cls.create_db()

        try:
            ledger_config = cls.load_ledger_config()
            column_type_map = cls._parse_config_types(ledger_config['header'])

            # Retrieve data from Google Sheets. You might change this
            # if you have your own flow or pass ledger ID/sheet name directly.
            data = service.get_ledger_data(force=force)

            cls._validate_numpy_data(data)
            with sqlite3.connect(str(DB_PATH)) as conn:
                cls._recreate_transactions_table(conn, data, column_type_map)
                cls._insert_data(conn, data, column_type_map)
                cls._update_meta_valid(conn)

            logging.info('Remote data was fetched and cached successfully.')
        except (RuntimeError, HttpError) as ex:
            cls.invalidate_cache(reason=f'Remote data pull failed: {ex}')
            raise RuntimeError(
                f'Failed to fetch or store remote data. Reason: {ex}'
            ) from ex

    @classmethod
    def clear_local_cache(cls) -> None:
        """
        Removes the entire local DB file from the system. After this operation,
        the cache will no longer exist.
        """
        if DB_PATH.exists():
            DB_PATH.unlink()
            logging.info('The local DB file was removed.')
        else:
            logging.info('No local DB file found to clear.')

    @classmethod
    def invalidate_cache(cls, reason: str) -> None:
        """
        Marks the cache as invalid by updating the meta table, but leaves existing data in place.
        Other parts of the application should treat an invalid cache as unusable until refreshed.

        Args:
            reason: A short explanation for why the cache is now invalid.
        """
        if not DB_PATH.exists():
            return

        with sqlite3.connect(str(DB_PATH)) as conn:
            if cls._table_exists(conn, TABLE_META):
                conn.execute(f"""
                    UPDATE {TABLE_META}
                    SET is_valid=0,
                        error_message=?
                    WHERE meta_id=1
                """, (reason,))
        logging.warning(f'The cache was marked invalid. Reason: {reason}')

    @classmethod
    def _table_exists(cls, conn: sqlite3.Connection, table_name: str) -> bool:
        """
        Determines if table_name exists in the connected SQLite database.
        Returns True if found; otherwise False.
        """
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None

    @classmethod
    def _get_cache_state(cls, conn: sqlite3.Connection) -> Dict[str, Any]:
        """
        Reads the meta table to learn if the cache is valid, when it was last synced,
        and any stored error messages. Returns a dictionary with keys:
        'last_sync' (datetime or None), 'is_valid' (bool), and 'error_message' (str or None).
        """
        state = {'last_sync': None, 'is_valid': False, 'error_message': None}
        if not cls._table_exists(conn, TABLE_META):
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

    @classmethod
    def _update_meta_valid(cls, conn: sqlite3.Connection) -> None:
        """
        Marks the cache as valid, clears any previous error message, and sets
        last_sync to the current UTC time.
        """
        now_str = datetime.datetime.utcnow().isoformat()
        conn.execute(f"""
            UPDATE {TABLE_META}
            SET is_valid=1,
                error_message=NULL,
                last_sync=?
            WHERE meta_id=1
        """, (now_str,))

    @classmethod
    def _is_stale(cls, last_sync: Optional[datetime.datetime]) -> bool:
        """
        Returns True if last_sync is missing or older than CACHE_MAX_AGE_DAYS.
        Otherwise returns False.
        """
        if not last_sync:
            return True
        age = datetime.datetime.utcnow() - last_sync
        return age.days >= CACHE_MAX_AGE_DAYS

    @classmethod
    def _validate_numpy_data(cls, data: np.ndarray) -> None:
        """
        Checks that 'data' has at least a header row and required columns.
        Raises RuntimeError if any conditions fail.
        """
        if data.size == 0 or data.shape[0] < 2:
            raise RuntimeError('Remote dataset is empty or missing a header row.')

        headers = [str(col).lower().strip() for col in data[0]]
        missing = [req for req in REQUIRED_COLUMNS if req not in headers]
        if missing:
            raise RuntimeError(
                f"Required columns {missing} were not found in the data. "
                f"Headers present: {headers}"
            )

    @classmethod
    def _recreate_transactions_table(
            cls,
            conn: sqlite3.Connection,
            data: np.ndarray,
            column_type_map: Dict[str, str]
    ) -> None:
        """
        Drops the existing transactions table if present, then creates a new one based on
        the headers in 'data' and the ledger.json type map. The table includes a local_id
        primary key, and each column name is quoted and escaped to handle special characters.
        """
        conn.execute(f'DROP TABLE IF EXISTS {TABLE_TRANSACTIONS}')

        headers = [str(col).strip() for col in data[0]]
        defs_list = ['"local_id" INTEGER PRIMARY KEY AUTOINCREMENT']

        for header in headers:
            col_name_raw = cls._sanitize_column_name(header)
            col_type = cls._infer_sqlite_type(header, column_type_map)
            # Escape any embedded double quotes, then wrap in double quotes
            col_name_escaped = col_name_raw.replace('"', '""')
            defs_list.append(f'"{col_name_escaped}" {col_type}')

        create_sql = f'CREATE TABLE "{TABLE_TRANSACTIONS}" (\n  {",".join(defs_list)}\n)'
        conn.execute(create_sql)

    @classmethod
    def _insert_data(
            cls,
            conn: sqlite3.Connection,
            data: np.ndarray,
            column_type_map: Dict[str, str]
    ) -> None:
        """
        Inserts rows from 'data' into the transactions table, performing any necessary
        type conversion. Column names are quoted and escaped to avoid syntax errors.
        """
        headers = [str(col).strip() for col in data[0]]
        rows = data[1:]

        # Convert each header to a properly escaped column name
        col_names = []
        for h in headers:
            raw_name = cls._sanitize_column_name(h)
            escaped = raw_name.replace('"', '""')  # Escape double quotes
            col_names.append(f'"{escaped}"')

        # Build the INSERT statement with quoted columns
        placeholders = ','.join(['?'] * len(col_names))
        insert_stmt = (
            f'INSERT INTO "{TABLE_TRANSACTIONS}" '
            f'({",".join(col_names)}) '
            f'VALUES ({placeholders})'
        )

        logging.info(f'Inserting {rows.shape[0]} rows into the "{TABLE_TRANSACTIONS}" table.')

        for row in rows:
            converted = [cls._convert_value(h, val, column_type_map) for h, val in zip(headers, row)]
            conn.execute(insert_stmt, converted)

    @classmethod
    def _sanitize_column_name(cls, header: str) -> str:
        """
        Returns a workable column name for SQLite, avoiding actual double quotes
        in the string. Special symbols like $€£ or / are left intact so long as
        they do not interfere with quoting.

        If the header is 'id' (case-insensitive), we rename it to 'remote_id'.
        Replaces spaces or periods with underscores. You can expand or change this
        to suit your naming conventions.
        """
        lower_header = header.lower()
        if lower_header == 'id':
            return 'remote_id'

        # For safer usage, replace spaces and periods with underscores:
        sanitized = header.strip().replace(' ', '_').replace('.', '_')
        return sanitized

    @classmethod
    def _infer_sqlite_type(cls, raw_header: str, type_map: Dict[str, str]) -> str:
        """
        Finds the appropriate SQLite type for 'raw_header' using the ledger.json type map.
        If a matching entry exists, it is mapped to an SQLite type. Otherwise, TEXT is used.
        """
        declared_type = cls._get_declared_type(raw_header, type_map)
        if declared_type == 'int':
            return 'INTEGER'
        elif declared_type == 'float':
            return 'REAL'
        elif declared_type == 'date':
            return 'TEXT'
        elif declared_type == 'string':
            return 'TEXT'
        return 'TEXT'

    @classmethod
    def _convert_value(cls, raw_header: str, value: Any, type_map: Dict[str, str]) -> Any:
        """
        Converts 'value' to an appropriate Python type based on the ledger.json config.

        - If 'date': Convert Google Sheets date serials (floats/integers) to ISO-8601 ("YYYY-MM-DD") text.
          If it's already a text date, try to parse it, or store raw if parsing fails.
        - If 'int': Convert empty strings to 0 or None on parse failure.
        - If 'float': Strip currency symbols and parse as float. Empty strings become 0.0.
        - Otherwise: treat as text.
        """
        if value is None:
            return None

        text_val = str(value).strip()
        declared_type = cls._get_declared_type(raw_header, type_map)

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
            # Remove currency symbols or commas
            text_val = (text_val
                        .replace(',', '')
                        .replace('£', '')
                        .replace('$', '')
                        .replace('€', ''))
            try:
                return float(text_val)
            except ValueError:
                logging.warning(f'Failed to parse "{text_val}" as float for column "{raw_header}". Storing None.')
                return None

        if declared_type == 'date':
            # Attempt to interpret numeric serial (Google Sheets date),
            # or parse textual date strings. Finally, store as "YYYY-MM-DD".
            if text_val == '':
                return ''  # or None, if you prefer blank dates to be null

            # 1) Try to interpret as a float-based serial date.
            #    Google Sheets typically uses "days since 1899-12-30" for date-only cells.
            try:
                # If the cell is purely numeric (e.g. "45674"), interpret as sheets date.
                serial_float = float(text_val)
                iso_date = cls._google_serial_date_to_iso(serial_float)
                return iso_date
            except ValueError:
                pass  # If it's not purely numeric, keep trying below.

            # 2) If that fails, try to parse textual date (e.g., "2023-06-15", "6/15/2023", etc.)
            #    For robust parsing, you might use dateutil, or just store the raw string.
            #    Here's a simple example using datetime.strptime for a known format:
            #    If your data can have many formats, consider using 'dateutil.parser'.
            try:
                dt = datetime.datetime.strptime(text_val, '%Y-%m-%d')
                return dt.strftime('%Y-%m-%d')  # Standardize to ISO
            except ValueError:
                # If we fail to parse, log a warning and just store the raw text or fallback
                logging.warning(f'Unable to parse "{text_val}" as a date for column "{raw_header}". Storing raw.')
                return text_val

        # Default for 'string' or if not recognized
        return text_val

    @classmethod
    def _google_serial_date_to_iso(cls, serial: float) -> str:
        """
        Converts a Google Sheets date serial to an ISO 'YYYY-MM-DD' string.
        Google Sheets date serials use 1899-12-30 as day 0 for date-only cells.
        If the serial is negative or otherwise suspicious, we store a blank or log a warning.
        """
        base_date = datetime.datetime(1899, 12, 30)
        # Some spreadsheets use day 1 as 1900-01-01, but typically Python docs + Google docs indicate 1899-12-30.
        # If your data is off by a day, you may need to shift by 1.

        # If it's a float like 45674.75, that .75 might indicate time-of-day. You can handle that or drop it.
        # For date-only cells, Sheets returns an integer. We'll keep the day portion only.
        day_offset = int(serial)

        if day_offset < -10000:  # Arbitrary cutoff for "not plausible"
            logging.warning(f'Serial date "{serial}" is suspiciously negative. Storing blank.')
            return ''

        converted_date = base_date + datetime.timedelta(days=day_offset)
        return converted_date.strftime('%Y-%m-%d')

    @classmethod
    def _parse_config_types(cls, header_config: Dict[str, str]) -> Dict[str, str]:
        """
        Reads the ledger.json "header" field to produce a dictionary mapping each column name
        to a declared type, such as 'int', 'float', 'date', or 'string'. Lookups will be done
        case-insensitively, so storing "ID": "int" in JSON will apply to the 'id' column.
        """
        parsed = {}
        for col_name, col_type in header_config.items():
            # Convert to lower for consistent matching; store user type in lower as well
            parsed[col_name.lower().strip()] = col_type.lower().strip()
        return parsed

    @classmethod
    def _get_declared_type(cls, raw_header: str, type_map: Dict[str, str]) -> str:
        """
        Returns the declared type from the ledger.json config for the specified header,
        ignoring case. Defaults to 'string' if nothing is declared.
        """
        lower_header = raw_header.lower().strip()
        if lower_header in type_map:
            return type_map[lower_header]
        return 'string'
