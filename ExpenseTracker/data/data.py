"""
Data Analytics API Module

This module provides a high-level interface for loading transaction data from the local
cache database, filtering and preparing it for analysis, and retrieving expenditure summaries.

Examples:
    >>> df = get_monthly_expenses('2023-06')
"""
import enum
import functools
import logging
import re

import pandas as pd

from ..core import database
from ..settings import lib


def _conform_to_header_mapping(df: pd.DataFrame) -> pd.DataFrame:
    config = lib.settings.get_section('mapping')
    if not config or not all(isinstance(v, str) for v in config.values()):
        logging.error('Invalid header mapping configuration found in config')
        return pd.DataFrame(columns=lib.DATA_MAPPING_KEYS)

    difference = set(lib.DATA_MAPPING_KEYS).difference(set(config.keys()))
    if difference:
        logging.error(f'Header mapping is missing keys: {difference}')
        return pd.DataFrame(columns=lib.DATA_MAPPING_KEYS)

    # Implement the merge syntax parsing here for column mapping definitions, like
    # description=Description+Notes+Account
    merge_mapping = {}
    for k, v in config.items():
        j = '\\'.join(lib.DATA_MAPPING_SEPARATOR_CHARS)
        for _v in re.split(fr'[\{j}]', v):
            if k not in merge_mapping:
                merge_mapping[k] = []
            merge_mapping[k].append(_v)

    # Create empty df
    new_df = pd.DataFrame(columns=lib.DATA_MAPPING_KEYS)

    for k, v in merge_mapping.items():
        new_df[k] = pd.Series(dtype='object')

        logging.debug(f'Merging columns {v} into {k}')

        if len(v) == 1:
            new_df[k] = df[v[0]].copy()
        else:
            new_df[k] = df[v].fillna('').astype(str).agg('\n'.join, axis=1)

    if set(new_df.columns.tolist()) != set(lib.DATA_MAPPING_KEYS):
        logging.error(f'DataFrame columns do not match the expected header mapping keys. '
                      f'Expected: {lib.DATA_MAPPING_KEYS}, Found: {df.columns.tolist()}')
        return pd.DataFrame(columns=lib.DATA_MAPPING_KEYS)

    return new_df


def _conform_date_column(df: pd.DataFrame) -> pd.DataFrame:
    df['date'] = pd.to_datetime(df['date'], format=database.DATE_COLUMN_FORMAT, errors='coerce')
    clean_df = df.dropna(subset=['date'])

    # Compare size before and after dropping Na values
    if len(df) != len(clean_df):
        logging.warning(
            f'Unparsable date formats encountered: Dropped {len(df) - len(clean_df)} rows with invalid date format.')

    # Check if the date column is empty after conversion
    if clean_df['date'].empty:
        logging.error('Date column is empty after conversion. No valid dates found.')
        return pd.DataFrame(columns=lib.DATA_MAPPING_KEYS)

    # Sort data by date
    clean_df = clean_df.sort_values(by='date', ascending=True).reset_index(drop=True)
    return clean_df


def _conform_amount_column(df: pd.DataFrame) -> pd.DataFrame:
    df['amount'] = pd.to_numeric(df['amount'], downcast='float', errors='coerce')

    l = len(df) - len(df.dropna(subset=['amount']))
    if l > 0:
        logging.warning(f'{l} rows have invalid amount amount values.')

    # Replace NaN values with 0
    df['amount'] = df['amount'].fillna(0)

    return df


def _conform_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in 'description', 'category', 'account':
        df[col] = df[col].fillna('').astype(str)
    return df


def _conform_period(df: pd.DataFrame, yearmonth: str, span: int) -> pd.DataFrame:
    start_period = pd.Period(yearmonth)
    target_periods = [start_period + i for i in range(span)]
    df_month = df[df['date'].dt.to_period('M').isin(target_periods)]
    return df_month


METADATA_KEYS = [
    'hide_empty_categories',
    'exclude_negative',
    'exclude_zero',
    'exclude_positive',
    'yearmonth',
    'span',
    'summary_mode',
]


class SummaryMode(enum.StrEnum):
    Total = 'total'
    Monthly = 'monthly'


def metadata():
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from ..settings import lib
            from ..core.database import database as db
            data = lib.settings.get_section('metadata')
            for key in METADATA_KEYS:
                if key in data:
                    kwargs[key] = data[key]
            db.verify()
            return func(db.data(), **kwargs)
        return wrapper
    return decorator

@metadata()
def get_data(
        df: pd.DataFrame,
        hide_empty_categories: bool = True,
        exclude_negative: bool = False,
        exclude_zero: bool = False,
        exclude_positive: bool = True,
        yearmonth: str = '2024-01',
        span: int = 1,
        summary_mode: str = SummaryMode.Total.value,
        add_total_row: bool = True,
) -> pd.DataFrame:
    """Load and wrap data from the database.

    """
    if df.empty:
        logging.warning('No data available in the database.')
        return pd.DataFrame(columns=lib.EXPENSE_DATA_COLUMNS)

    # Span must be a minimum of 1 month
    span = int(span) if span else 1
    if span < 1:
        span = 1

    df = _conform_to_header_mapping(df)
    df = _conform_date_column(df)
    df = _conform_amount_column(df)
    df = _conform_string_columns(df)
    df = _conform_period(df, yearmonth, span)

    if exclude_zero:
        logging.debug('Excluding zero amounts')
        df = df[df['amount'] != 0]
    if exclude_negative:
        logging.debug('Excluding negative amounts')
        df = df[df['amount'] >= 0]
    if exclude_positive:
        logging.debug('Excluding positive amounts')
        df = df[df['amount'] <= 0]

    config = lib.settings.get_section('mapping')
    transaction_columns = list(config.keys())

    breakdown = (
        df.groupby('category')
        .apply(
            lambda _df: pd.Series({
                'total': _df['amount'].sum(),
                'transactions': _df[transaction_columns].to_dict(orient='records')
            }))
        .reset_index()
    )

    # Normalize the total column
    if summary_mode == SummaryMode.Monthly.value:
        breakdown['total'] = breakdown['total'] / span

    # Hide empty categories
    if hide_empty_categories:
        breakdown = breakdown[breakdown['category'].notna() & (breakdown['category'] != '')]

    # Sort by total amount
    breakdown = breakdown.sort_values('category', ascending=True).reset_index(drop=True)

    # Add total row
    if add_total_row:
        total = breakdown['total'].sum()
        breakdown = pd.concat([breakdown, pd.DataFrame({'category': ['Total'], 'total': [total]})], ignore_index=True)


    return breakdown
