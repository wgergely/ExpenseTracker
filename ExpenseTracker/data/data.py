"""
Data Analytics API Module

This module provides a high-level interface for loading transaction data from the local
cache database, filtering and preparing it for analysis, and retrieving expenditure summaries.

Examples:
    >>> df = get_monthly_expenses("2023-06")
"""
import logging
import re

import pandas as pd

from ..database.database import get_cached_data, DATABASE_DATE_FORMAT
from ..settings import lib

logging.basicConfig(level=logging.INFO)

EXPENSES_COLUMNS =['category', 'total', 'transactions']


def _conform_to_header_mapping(df: pd.DataFrame) -> pd.DataFrame:
    config = lib.settings.get_section('data_header_mapping')
    if not config or not all(isinstance(v, str) for v in config.values()):
        logging.error('Invalid header mapping configuration found in config')
        return pd.DataFrame(columns=lib.DATA_MAPPING_KEYS)

    difference = set(lib.DATA_MAPPING_KEYS).difference(set(config.keys()))
    if difference:
        logging.error(f'Header mapping is missing keys: {difference}')
        return pd.DataFrame(columns=lib.DATA_MAPPING_KEYS)

    # Create a `target = [sources]` mapping for mapping merge requests
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

        logging.info(f'Merging columns {v} into {k}')

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
    df['date'] = pd.to_datetime(df['date'], format=DATABASE_DATE_FORMAT, errors='coerce')
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


def conform_cached_data(
        df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Conforms the cached data to a standard format for further processing.

    Args:
        df: The raw DataFrame loaded from the cache.
        years_back: Number of years of data to retain. Default is 5.

    Returns:
        A DataFrame containing only the relevant rows and columns for expense analytics.
    """
    if df.empty:
        logging.warning('Cached data is empty, nothing to conform.')
        return pd.DataFrame(columns=lib.DATA_MAPPING_KEYS)

    df = _conform_to_header_mapping(df)
    df = _conform_date_column(df)
    df = _conform_amount_column(df)
    df = _conform_string_columns(df)

    return df

    # try:
    #     # Parse dates as UTC-aware then remove timezone to yield naive datetimes
    #     df['date'] = pd.to_datetime(df['date'], errors='coerce', utc=True).dt.tz_localize(None)
    # except Exception as ex:
    #     logging.error(f'Error parsing dates: {ex}')
    #     return pd.DataFrame()
    # df = df.dropna(subset=['date'])
    #
    # # Use a naive datetime for cutoff_date by removing timezone info
    # today = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    # try:
    #     cutoff_date = today.replace(year=today.year - years_back)
    # except ValueError:
    #     cutoff_date = today - datetime.timedelta(days=years_back * 365)
    # df = df[df['date'] >= cutoff_date]
    #
    # categories_config = lib.settings.get_section('categories')
    # if not categories_config:
    #     logging.error('No categories found in config')
    #     return pd.DataFrame()
    # excluded_categories = {cat for cat, info in categories_config.items() if info.get('excluded', False)}
    # df['category'] = df['category'].fillna('Miscellaneous')
    # df = df[~df['category'].isin(excluded_categories)]
    #
    # try:
    #     df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    # except Exception as ex:
    #     logging.error(f'Error converting amounts to numeric: {ex}')
    #     return pd.DataFrame()
    # df = df.dropna(subset=['amount'])
    #
    # logging.info(
    #     f'Prepared a DataFrame of {len(df)} expense rows from the last {years_back} years, '
    #     f'excluding categories: {sorted(excluded_categories)}.'
    # )
    # return df


def get_monthly_expenses(year_month: str, sort_column: str = 'category', span: int = 1) -> pd.DataFrame:
    """
    Returns a detailed breakdown by category for the specified period starting at year_month
    (format: 'YYYY-MM') and spanning a given number of months using exclusively pandas operations.
    For each category, the resulting DataFrame contains:
      - "category": the category name,
      - "total": the sum of all expenses in that category,
      - "transactions": a list of transaction objects for that category. Each transaction object
        includes only the keys defined in the ledger.json "data_header_mapping".

    Args:
        year_month: A string representing the starting target month in 'YYYY-MM' format.
        sort_column: The column to sort the resulting DataFrame by. Default is 'category'.
        span: Number of months to include starting from the given year_month. Defaults to 1.

    Returns:
        A pandas DataFrame with columns ['category', 'total', 'transactions']. If no data exists
        for the specified period, an empty DataFrame is returned.
    """
    df = get_cached_data()
    df = conform_cached_data(df)
    if df.empty:
        logging.warning('No cached data available. Returning empty DataFrame.')
        return pd.DataFrame(columns=['category', 'total', 'transactions'])

    span = int(span) if span else 1
    if span < 1:
        span = 1

    start_period = pd.Period(year_month)

    target_periods = [start_period + i for i in range(span)]
    df_month = df_prepared[df_prepared['date'].dt.to_period('M').isin(target_periods)]
    if df_month.empty:
        return pd.DataFrame(columns=['category', 'total', 'transactions'])

    df_month = df_month[df_month['amount'] < 0]

    mapping = lib.settings.get_section('data_header_mapping')
    desired_keys = list(mapping.keys())

    breakdown = (
        df_month.groupby('category')
        .apply(lambda g: pd.Series({
            'total': g['amount'].sum(),
            'transactions': g[desired_keys].to_dict(orient='records')
        }))
        .reset_index()
    )
    breakdown = breakdown[breakdown['category'].notna() & (breakdown['category'] != '')]
    breakdown = breakdown.sort_values(sort_column, ascending=True).reset_index(drop=True)
    return breakdown
