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
from ..settings import locale

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


def _calculate_weights(df: pd.DataFrame,
                       exclude_negative: bool,
                       exclude_positive: bool,
                       min_weight: float = 0.02) -> pd.DataFrame:
    """Calculate and assign normalized weights for each row in df (grouped by category).
    0.0 = pivot value (e.g. zero or min/max), 1.0 = dataset extreme.

    Args:
        df: The dataframe after grouping by category (and possibly a 'Total' row).
        exclude_negative: Whether negative amounts were excluded from the dataset.
        exclude_positive: Whether positive amounts were excluded from the dataset.
        min_weight: The minimum weight to assign to non-zero rows (e.g. 0.05).

    Returns:
        df: The same dataframe with a new 'weight' column updated.
    """
    # Exclude any "Total" row from min/max analysis
    core_df = df[df['category'] != 'Total']
    if core_df.empty:
        return df

    min_val = core_df['total'].min()
    max_val = core_df['total'].max()

    def clamp_weight(w: float, row_total: float) -> float:
        # Clamp 0 ≤ w ≤ 1
        w_clamped = max(0.0, min(w, 1.0))
        # If total isn't zero, ensure at least min_weight
        if row_total != 0:
            w_clamped = max(w_clamped, min_weight)
        return w_clamped

    def weight_neg(row_total):
        # for example pivot=0, extreme=min_val (which is negative or zero)
        # row_total / min_val => 0..1  (largest negative becomes 1.0, zero => 0)
        if min_val == 0:
            return 0.0
        w = row_total / min_val
        return clamp_weight(w, row_total)

    def weight_pos(row_total):
        # pivot=0, extreme=max_val => row_total / max_val => 0..1
        if max_val == 0:
            return 0.0
        w = row_total / max_val
        return clamp_weight(w, row_total)

    def weight_both(row_total):
        # Standard min–max => (row_total - min_val) / (max_val - min_val)
        denom = max_val - min_val
        if denom == 0:
            return 0.0
        w = (row_total - min_val) / denom
        return clamp_weight(w, row_total)

    if exclude_positive and not exclude_negative:
        # All data <= 0 -> negative weighting
        df.loc[df['category'] != 'Total', 'weight'] = df['total'].apply(weight_neg)
    elif exclude_negative and not exclude_positive:
        # All data >= 0 -> positive weighting
        df.loc[df['category'] != 'Total', 'weight'] = df['total'].apply(weight_pos)
    else:
        # Mixed data -> min–max
        df.loc[df['category'] != 'Total', 'weight'] = df['total'].apply(weight_both)

    return df


def _build_description(_df, _locale):
    try:
        total_val = _df['amount'].sum()
        total_str = locale.format_currency_value(total_val, _locale)
        accounts_str = ', '.join(_df.get('account', pd.Series()).unique())

        # Example: smallest 3 by raw 'amount'
        _max = _df.nsmallest(3, 'amount')
        _max_str = ', '.join([
            f'{locale.format_currency_value(row["amount"], _locale)} ({row["description"]})'
            for _, row in _max.iterrows()
        ])

        return (
            f'Category: {", ".join(_df["category"].unique())}\n'
            f'Total: {total_str}\n'
            f'Accounts: {accounts_str}\n\n'
            f'Transactions:\n\n{_max_str}...'
        )
    except Exception as e:
        logging.debug(f'Error building description: {e}')
        return ''


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

    # Ensure span is at least 1
    span = max(int(span) if span else 1, 1)

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

    # Fallback locale
    _locale = lib.settings['locale']
    if _locale not in locale.LOCALE_MAP:
        _locale = 'en_GB'

    # Group by category; aggregate totals & build transaction list
    if not df.empty:
        df = (
            df.groupby('category')
            .apply(
                lambda _df: pd.Series({
                    'total': _df['amount'].sum(),
                    'transactions': _df[transaction_columns].to_dict(orient='records'),
                    'description': _build_description(_df, _locale),
                    'weight': 0.0,  # Will be filled by _calculate_weights
                })
            )
            .reset_index()
        )
    else:
        df = pd.DataFrame(columns=['category', 'total', 'transactions', 'description', 'weight'])

    # add missing categories
    if not hide_empty_categories:
        categories = lib.settings.get_section('categories')
        for category in categories:
            if category not in df['category'].values:
                df = pd.concat([df, pd.DataFrame({'category': [category], 'total': [0.0]})], ignore_index=True)

    # Normalize the total column if monthly
    if summary_mode == SummaryMode.Monthly.value:
        df['total'] = df['total'] / span

    # Hide empty categories
    if hide_empty_categories:
        df = df[df['category'].notna() & (df['category'] != '')]

    # Sort categories
    df = df.sort_values('category', ascending=True).reset_index(drop=True)

    # Remove excluded categories
    config = lib.settings.get_section('categories')
    excluded = [k for k, v in config.items() if v['excluded']]
    if excluded:
        df = df[~df['category'].isin(excluded)]

    # Calculate weights
    df = _calculate_weights(df, exclude_negative, exclude_positive, min_weight=0.02)

    # add total row
    if add_total_row:
        overall = df['total'].sum()
        df = pd.concat(
            [df, pd.DataFrame({'category': ['Total'], 'total': [overall]})],
            ignore_index=True
        )

    return df
