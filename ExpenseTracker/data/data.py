"""
Data Analytics API Module

This module provides a high-level interface for loading transaction data from the local
cache database, filtering and preparing it for analysis, and retrieving expenditure summaries.

Examples:
    >>> df = get_monthly_expenses("2023-06")
"""

import datetime
import logging

import pandas as pd

from ..database.database import load_config, get_cached_data

logging.basicConfig(level=logging.INFO)


def _prepare_expenses_dataframe(df: pd.DataFrame, years_back: int = 5) -> pd.DataFrame:
    """
    Prepares a DataFrame for expense analytics by:
      - Renaming columns based on the ledger.json "data_header_mapping" configuration.
      - Parsing the date column as datetime.
      - Filtering out rows older than 'years_back' years.
      - Excluding rows with categories marked as excluded in the config.
      - Converting the amount column to numeric and dropping invalid rows.

    Args:
        df: The raw DataFrame loaded from the cache.
        years_back: Number of years of data to retain. Default is 5.

    Returns:
        A DataFrame containing only the relevant rows and columns for expense analytics.
    """
    if df.empty:
        return df

    # Load configuration to get header mapping and category exclusions.
    config = load_config()
    mapping = config.get('data_header_mapping', {})
    if not mapping:
        logging.error('No data_header_mapping found in config; returning empty DataFrame.')
        return pd.DataFrame()

    # Ensure required analytic fields are defined in the config.
    analytics_required = {"date", "amount", "category"}
    missing_required = analytics_required - set(mapping.keys())
    if missing_required:
        logging.error("Config missing required analytic fields: " + ", ".join(missing_required))
        return pd.DataFrame()

    # Build a source-to-destination renaming map.
    rename_map = {source: dest for dest, source in mapping.items()}
    missing_sources = [src for src in rename_map if src not in df.columns]
    if missing_sources:
        logging.error(
            f"Missing required source columns in data. Expected source columns (from config): {list(mapping.values())}; "
            f"missing: {missing_sources}; found columns: {list(df.columns)}"
        )
        return pd.DataFrame()
    df.rename(columns=rename_map, inplace=True)

    # Verify that the required analytic columns exist after renaming.
    for col in analytics_required:
        if col not in df.columns:
            logging.warning(f"No '{col}' column found after renaming; returning empty DataFrame.")
            return pd.DataFrame()

    try:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
    except Exception as ex:
        logging.error(f'Error parsing dates: {ex}')
        return pd.DataFrame()
    df = df.dropna(subset=['date'])

    today = datetime.datetime.utcnow().date()
    try:
        cutoff_date = today.replace(year=today.year - years_back)
    except ValueError:
        cutoff_date = today - datetime.timedelta(days=years_back * 365)
    df = df[df['date'] >= pd.to_datetime(cutoff_date)]

    # Load excluded categories from config.
    categories_config = config.get('categories', {})
    excluded_categories = {cat for cat, info in categories_config.items() if info.get('excluded', False)}
    df['category'] = df['category'].fillna('Miscellaneous')
    df = df[~df['category'].isin(excluded_categories)]

    try:
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    except Exception as ex:
        logging.error(f'Error converting amounts to numeric: {ex}')
        return pd.DataFrame()
    df = df.dropna(subset=['amount'])

    logging.info(
        f'Prepared a DataFrame of {len(df)} expense rows from the last {years_back} years, '
        f'excluding categories: {sorted(excluded_categories)}.'
    )
    return df


def get_monthly_expenses(year_month: str) -> pd.DataFrame:
    """
    Returns a detailed breakdown by category for the specified year_month (format: 'YYYY-MM')
    using exclusively pandas operations. For each category, the resulting DataFrame contains:
      - "category": the category name,
      - "total": the sum of all expenses in that category,
      - "transactions": a list of transaction objects for that category. Each transaction object
        includes only the keys defined in the ledger.json "data_header_mapping".

    Args:
        year_month: A string representing the target month in 'YYYY-MM' format.

    Returns:
        A pandas DataFrame with columns ['category', 'total', 'transactions']. If no data exists
        for the specified month, an empty DataFrame is returned.
    """
    df_raw = get_cached_data()
    df_prepared = _prepare_expenses_dataframe(df_raw)
    if df_prepared.empty:
        return pd.DataFrame(columns=['category', 'total', 'transactions'])

    try:
        target_period = pd.Period(year_month)
    except ValueError:
        logging.warning(f"Invalid year_month format: {year_month}. Use 'YYYY-MM'. Returning empty DataFrame.")
        return pd.DataFrame(columns=['category', 'total', 'transactions'])

    df_month = df_prepared[df_prepared['date'].dt.to_period('M') == target_period]
    if df_month.empty:
        return pd.DataFrame(columns=['category', 'total', 'transactions'])

    # Load header mapping from config to determine desired transaction keys.
    config = load_config()
    mapping = config.get('data_header_mapping', {})
    desired_keys = list(mapping.keys())

    # Group by category and aggregate totals and transactions using pandas.
    breakdown = (
        df_month.groupby('category')
        .apply(lambda g: pd.Series({
            'total': g['amount'].sum(),
            'transactions': g[desired_keys].to_dict(orient='records')
        }))
        .reset_index()
    )
    breakdown = breakdown.sort_values('total', ascending=False).reset_index(drop=True)
    return breakdown
