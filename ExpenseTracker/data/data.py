"""Data analytics API for transaction analysis.

This module provides a high-level interface for loading transaction data from the local cache
database, filtering and preparing it for analysis, and retrieving expenditure summaries.
"""
import enum
import functools
import logging
import re
from typing import Optional

import pandas as pd
from statsmodels.nonparametric.smoothers_lowess import lowess

from ..core import database
from ..settings import lib
from ..settings import locale
from ..status.status import BaseStatusException

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
    """Decorator to inject metadata settings and verify database connectivity.

    Retrieves metadata settings from configuration and verifies the database before calling
    the wrapped function.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from ..settings import lib
            from ..core.database import database as db
            data = lib.settings.get_section('metadata')
            for key in METADATA_KEYS:
                if key in data:
                    kwargs[key] = data[key]

            try:
                db.verify()
            except BaseStatusException:
                return pd.DataFrame()
            return func(db.data(), **kwargs)

        return wrapper

    return decorator


def _strict_header_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """Map and reorder DataFrame columns based on configuration.

    Returns a DataFrame with exactly the columns defined in the 'mapping' section of the config
    (in the order of lib.TRANSACTION_DATA_COLUMNS). Columns in the file but not in mapping are
    discarded. Columns specified in mapping but missing in the file create empty Series. Merge
    syntax for combined fields is supported.

    Args:
        df (pd.DataFrame): Input DataFrame with raw columns.

    Returns:
        pd.DataFrame: DataFrame with strict header mapping.
    """
    cfg = lib.settings.get_section('mapping')
    if not cfg:
        logging.error('Header mapping missing in config')
        return pd.DataFrame(columns=lib.TRANSACTION_DATA_COLUMNS)

    # build a merge-map → {internal_key: [raw_col1, raw_col2, etc.]}
    merge_map: dict[str, list[str]] = {key: [] for key in lib.DATA_MAPPING_KEYS}
    j = r"|".join(map(re.escape, lib.DATA_MAPPING_SEPARATOR_CHARS))
    for internal_key, raw_spec in cfg.items():
        for raw in re.split(j, raw_spec):
            merge_map.setdefault(internal_key, []).append(raw)

    # Build a DataFrame with exactly the configured mapping keys,
    # preserving index for any additional columns like local_id
    out = pd.DataFrame(columns=lib.TRANSACTION_DATA_COLUMNS)
    for internal_key, raw_cols in merge_map.items():
        present = [c for c in raw_cols if c in df.columns]
        if not present:
            # missing column → create empty
            out[internal_key] = pd.Series(dtype='object')
            continue
        if len(present) == 1:
            out[internal_key] = df[present[0]].copy()
        else:
            out[internal_key] = df[present].fillna("").astype(str).agg("\n".join, axis=1)

    # Preserve local_id if present in the source df
    if 'local_id' in df.columns:
        out['local_id'] = df['local_id']

    return out


def _conform_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """Convert 'date' column to datetime, drop invalid entries, and sort.

    Parses the 'date' column using the database.DATE_COLUMN_FORMAT, drops rows with invalid
    dates, logs warnings for parsing failures, and returns a sorted DataFrame.

    Args:
        df (pd.DataFrame): DataFrame with a 'date' column.

    Returns:
        pd.DataFrame: DataFrame sorted by 'date' with valid datetime entries.
    """
    df['date'] = pd.to_datetime(df['date'], format=database.DATE_COLUMN_FORMAT, errors='coerce')
    clean_df = df.dropna(subset=['date'])

    # Compare size before and after dropping Na values
    if len(df) != len(clean_df):
        logging.warning(
            f'Unparsable date formats encountered: Dropped {len(df) - len(clean_df)} rows with invalid date format.')

    # Check if the date column is empty after conversion
    if clean_df['date'].empty:
        logging.error('Date column is empty after conversion. No valid dates found.')
        return pd.DataFrame(columns=lib.TRANSACTION_DATA_COLUMNS)

    # Sort data by date
    clean_df = clean_df.sort_values(by='date', ascending=True).reset_index(drop=True)
    return clean_df


def _conform_amount_column(df: pd.DataFrame) -> pd.DataFrame:
    """Convert 'amount' column to numeric, handle invalid values, and fill NaNs.

    Converts the 'amount' column to numeric floats, logs warnings for invalid values, replaces
    NaNs with zero, and returns the DataFrame.

    Args:
        df (pd.DataFrame): DataFrame with an 'amount' column.

    Returns:
        pd.DataFrame: DataFrame with numeric 'amount' values.
    """
    df['amount'] = pd.to_numeric(df['amount'], downcast='float', errors='coerce')

    l = len(df) - len(df.dropna(subset=['amount']))
    if l > 0:
        logging.warning(f'{l} rows have invalid amount amount values.')

    # Replace NaN values with 0
    df['amount'] = df['amount'].fillna(0)

    return df


def _conform_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure string columns have no missing values and are of type str.

    Fills NaNs in description, category, and account columns with empty strings and casts them
    to string type.

    Args:
        df (pd.DataFrame): DataFrame with potential string columns.

    Returns:
        pd.DataFrame: DataFrame with standardized string columns.
    """
    for col in 'description', 'category', 'account':
        df[col] = df[col].fillna('').astype(str)
    return df


def _conform_period(df: pd.DataFrame, yearmonth: str, span: int) -> pd.DataFrame:
    """Filter DataFrame to a specified period range.

    Selects rows where 'date' falls within the span of months starting at yearmonth.

    Args:
        df (pd.DataFrame): DataFrame with a 'date' column of datetime type.
        yearmonth (str): Starting year-month in 'YYYY-MM' format.
        span (int): Number of months to include.

    Returns:
        pd.DataFrame: Filtered DataFrame within the specified period.
    """
    start_period = pd.Period(yearmonth)
    target_periods = [start_period + i for i in range(span)]
    df_month = df[df['date'].dt.to_period('M').isin(target_periods)]
    return df_month


def _calculate_weights(df: pd.DataFrame,
                       exclude_negative: bool,
                       exclude_positive: bool,
                       min_weight: float = 0.02) -> pd.DataFrame:
    """Calculate and assign normalized weights for each row in a grouped DataFrame.

    Weights range from 0 to 1, based on min-max normalization of the 'total' column within
    each category, with a minimum non-zero weight.

    Args:
        df (pd.DataFrame): DataFrame after grouping by category (and possibly including a 'Total' row).
        exclude_negative (bool): Whether negative totals were excluded from the dataset.
        exclude_positive (bool): Whether positive totals were excluded from the dataset.
        min_weight (float): Minimum weight to assign to non-zero rows.

    Returns:
        pd.DataFrame: The same DataFrame with an additional 'weight' column.
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
    """Build a summary description string for a category's transactions.

    Constructs a description including category name, total amount, accounts involved, and sample
    transactions.

    Args:
        _df (pd.DataFrame): DataFrame containing transactions for a single category.
        _locale (str): Locale code for formatting currency values.

    Returns:
        str: Formatted description string, or empty string on error.
    """
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
    """Load and prepare transaction data for analysis.

    Loads transaction data, applies column mapping, type conversions, period filtering,
    and category aggregations, then calculates weights and optionally adds a total row.

    Args:
        df (pd.DataFrame): Raw transaction data.
        hide_empty_categories (bool): Hide categories with no transactions.
        exclude_negative (bool): Exclude negative amount transactions.
        exclude_zero (bool): Exclude zero amount transactions.
        exclude_positive (bool): Exclude positive amount transactions.
        yearmonth (str): Starting year-month in 'YYYY-MM' format.
        span (int): Number of months to include in the analysis.
        summary_mode (str): Summary mode, either 'total' or 'monthly'.
        add_total_row (bool): Append a total summary row to the result.

    Returns:
        pd.DataFrame: Prepared DataFrame with columns ['category', 'total', 'transactions',
            'description', 'weight'] and an optional total row.
    """
    if df.empty:
        logging.warning('No data available in the database.')
        return pd.DataFrame(columns=lib.EXPENSE_DATA_COLUMNS)

    # Ensure span is at least 1
    span = max(int(span) if span else 1, 1)

    df = (
        _strict_header_mapping(df)
        .pipe(_conform_date_column)
        .pipe(_conform_amount_column)
        .pipe(_conform_string_columns)
        .pipe(_conform_period, yearmonth, span)
    )

    if exclude_zero:
        logging.debug('Excluding zero amounts')
        df = df[df['amount'] != 0]
    if exclude_negative:
        logging.debug('Excluding negative amounts')
        df = df[df['amount'] >= 0]
    if exclude_positive:
        logging.debug('Excluding positive amounts')
        df = df[df['amount'] <= 0]

    # Use fixed transaction columns (including local_id) for record payloads
    transaction_columns = lib.TRANSACTION_DATA_COLUMNS.copy()

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

    # Preserve custom category order defined in configuration
    config = lib.settings.get_section('categories')
    order = list(config.keys())
    # Assign ordering index, unknown categories go to end
    df['__order'] = df['category'].apply(lambda x: order.index(x) if x in order else len(order))
    df = df.sort_values('__order').drop(columns='__order').reset_index(drop=True)

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


@metadata()
def get_trends(
        df: pd.DataFrame,
        category: Optional[str] = None,
        hide_empty_categories: bool = True,  # unused
        exclude_negative: bool = False,
        exclude_zero: bool = False,
        exclude_positive: bool = True,
        yearmonth: str = "",
        span: int = 1,
        negative_span: int = 3,
        summary_mode: str = SummaryMode.Total.value,
        loess_fraction: float = 0.15,
) -> pd.DataFrame:
    """Compute monthly spending trends with smoothing.

    Aggregates transaction amounts into monthly totals for each category (or a single category),
    applies LOESS smoothing, and returns trend data within a specified period range.

    Args:
        df (pd.DataFrame): Input DataFrame with 'amount', 'category', and 'date' columns.
        category (Optional[str]): Category to filter. If None, computes trends for all categories.
        hide_empty_categories (bool): Currently unused flag to hide categories with no data.
        exclude_negative (bool): Exclude negative amount transactions.
        exclude_zero (bool): Exclude zero amount transactions.
        exclude_positive (bool): Exclude positive amount transactions.
        yearmonth (str): Year-month 'YYYY-MM' to center the trend window; uses latest period if empty.
        span (int): Forward span in months for trend computation.
        negative_span (int): Backward span in months for trend computation.
        summary_mode (str): Summary mode; maintained for compatibility.
        loess_fraction (float): Fraction of data for LOESS smoothing (0 < loess_fraction <= 1).

    Returns:
        pd.DataFrame: Trend data with columns ['category', 'month', 'loess', 'monthly_total'].
    """
    # conform input
    df2 = (
        _strict_header_mapping(df)
        .pipe(_conform_date_column)
        .pipe(_conform_amount_column)
        .pipe(_conform_string_columns)
    )
    if df2.empty:
        return pd.DataFrame(columns=lib.TREND_DATA_COLUMNS)
    # apply amount filters
    if exclude_zero:
        df2 = df2[df2['amount'] != 0]
    if exclude_negative:
        df2 = df2[df2['amount'] >= 0]
    if exclude_positive:
        df2 = df2[df2['amount'] <= 0]
    if df2.empty:
        return pd.DataFrame(columns=lib.TREND_DATA_COLUMNS)
    # restrict to category
    if category:
        df2 = df2[df2['category'] == category]
    # compute period
    df2['period'] = df2['date'].dt.to_period('M')
    # pivot period
    pivot = pd.Period(yearmonth) if yearmonth else df2['period'].max()
    # compute window
    neg = max(int(negative_span), 0)
    start = pivot - (neg - 1) if neg > 0 else pivot
    fwd = int(max(span, 1))
    end = pivot + (fwd - 1)
    periods = pd.period_range(start, end, freq='M')
    # group and sum
    if category:
        # single category
        grp = df2.groupby('period')['amount'].sum()
        series = grp.reindex(periods, fill_value=0)
        df_monthly = pd.DataFrame({
            'category': category,
            'period': series.index,
            'monthly_total': series.values,
        })
    else:
        cats = df2['category'].unique()
        idx = pd.MultiIndex.from_product([cats, periods], names=['category', 'period'])
        grp = df2.groupby(['category', 'period'])['amount'].sum()
        df_monthly = grp.reindex(idx, fill_value=0).rename('monthly_total').reset_index()
    # smoothing and build output
    rows = []
    for cat, sub in df_monthly.groupby('category'):
        vals = sub['monthly_total'].values
        m = len(vals)

        # LOESS smoothing
        if m < 3:
            loess_vals = vals.copy()
        else:
            x = pd.RangeIndex(stop=m)
            loess_vals = lowess(vals, x, frac=loess_fraction, return_sorted=False)
        df_out = pd.DataFrame({
            'category': cat,
            'period': periods,
            'monthly_total': vals,
            'loess': loess_vals,
        })
        rows.append(df_out)
    df_trends = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if df_trends.empty:
        return pd.DataFrame(columns=lib.TREND_DATA_COLUMNS)
    # timestamp for plotting
    df_trends['month'] = df_trends['period'].dt.to_timestamp('M')
    return df_trends[lib.TREND_DATA_COLUMNS]
