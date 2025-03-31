"""
Data Analytics API Module

This module provides a high-level interface for loading transaction data from the local
cache database, filtering and preparing it for analysis, and retrieving
monthly or category-based expenditure summaries. The goal is to enable a future UI front-end
to query spending trends easily.

We focus on the last 5 years of data and use only the "€€€" (Eur) column for amounts.
Categories such as "Transfers", "Income", and "Tax & Social Security" are excluded from
expense calculations. Everything else is considered part of personal expenses.

"""

import logging
import sqlite3
import datetime
from typing import Optional
import pandas as pd

from ..database.database import DB_PATH, LocalCacheManager

logging.basicConfig(level=logging.INFO)


# Categories that should be excluded from expense analytics
# (e.g. "Transfers", "Income", "Tax & Social Security")
EXCLUDED_CATEGORIES = {
    "Transfers",
    "Income",
    "Tax & Social Security"
}

def load_transactions() -> pd.DataFrame:
    """
    Loads all rows from the 'transactions' table in the local cache database into a pandas
    DataFrame. The DataFrame will contain columns matching the ledger definition, e.g.:
        remote_id, Date, Original_Description, Category, €€€, etc.

    If the local cache DB is invalid or missing, returns an empty DataFrame.

    Returns:
        A pandas DataFrame with all columns from the transactions table.
    """
    if not LocalCacheManager.verify_db():
        logging.warning("Local cache DB is invalid or missing. Returning an empty DataFrame.")
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(str(DB_PATH))
        df = pd.read_sql_query("SELECT * FROM transactions", conn)
    except sqlite3.Error as ex:
        logging.error(f"Error reading from local DB: {ex}")
        return pd.DataFrame()
    finally:
        if 'conn' in locals():
            conn.close()

    logging.info(f"Loaded {len(df)} rows from the 'transactions' table.")
    return df


def prepare_expenses_dataframe(
    df: pd.DataFrame,
    years_back: int = 5
) -> pd.DataFrame:
    """
    Prepares a DataFrame for expense analytics by:
      - Ensuring a 'date' column is parsed as datetime.
      - Filtering out rows older than 'years_back' years from today.
      - Excluding categories that are not relevant to personal expenses (Transfers, Income, Tax, etc.).
      - Renaming the '€€€' column to 'amount' for clarity.
      - Dropping rows without a valid date or amount.

    Args:
        df: The raw DataFrame loaded from the local DB.
        years_back: How many years of data to keep, counting from today's date. Defaults to 5.

    Returns:
        A DataFrame containing only the relevant rows and columns for expense analytics.
    """
    if df.empty:
        return df

    # Standardize column names to lowercase for convenience
    df.columns = [c.lower() for c in df.columns]

    # Convert 'date' to datetime. Some rows might be invalid or empty. We'll coerce them to NaT.
    if 'date' not in df.columns:
        logging.warning("No 'date' column found in DataFrame; returning empty.")
        return pd.DataFrame()

    df['date'] = pd.to_datetime(df['date'], errors='coerce')

    # Filter out rows with no valid date
    df = df.dropna(subset=['date'])

    # Compute a cutoff date for 'years_back'
    today = datetime.datetime.utcnow().date()
    cutoff_date = today.replace(year=today.year - years_back)
    # Keep only rows >= cutoff_date
    df = df[df['date'] >= pd.to_datetime(cutoff_date)]

    # Exclude categories we don't want counted as expenses
    if 'category' not in df.columns:
        logging.warning("No 'category' column found; returning empty.")
        return pd.DataFrame()

    df['category'] = df['category'].fillna('Miscellaneous')
    mask_excluded = df['category'].isin(EXCLUDED_CATEGORIES)
    df = df[~mask_excluded]

    # Rename the "€€€" column to "amount" if it exists
    # and parse it to float if not already.
    if '€€€' not in df.columns:
        logging.warning("No '€€€' column found for amounts; returning empty.")
        return pd.DataFrame()
    df.rename(columns={'€€€': 'amount'}, inplace=True)

    # Convert amounts to float, dropping rows that fail conversion
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df = df.dropna(subset=['amount'])

    # If you want negative amounts for expenses, you could do it here:
    # df['amount'] = df['amount'] * -1

    logging.info(
        f"Prepared a DataFrame of {len(df)} expense rows from the last {years_back} years, "
        f"excluding categories {EXCLUDED_CATEGORIES}."
    )
    return df


def get_monthly_expenses(df: pd.DataFrame) -> pd.DataFrame:
    """
    Groups expenses by Year-Month and calculates total monthly spending.
    The DataFrame is expected to have a valid 'date' column and an 'amount' column.

    Args:
        df: A prepared DataFrame containing date and amount columns.

    Returns:
        A DataFrame with columns: ['year_month', 'total_spend'] sorted by year_month ascending.
        Each row represents the total sum of amounts for that month.
    """
    if df.empty:
        return pd.DataFrame(columns=['year_month', 'total_spend'])

    if 'date' not in df.columns or 'amount' not in df.columns:
        logging.warning("DataFrame lacks required columns 'date' or 'amount'. Returning empty.")
        return pd.DataFrame(columns=['year_month', 'total_spend'])

    # Create a 'year_month' column (type Period) from 'date'
    df['year_month'] = df['date'].dt.to_period('M')
    monthly = df.groupby('year_month')['amount'].sum().reset_index()
    monthly.rename(columns={'amount': 'total_spend'}, inplace=True)

    # Convert Period back to string for a cleaner result
    monthly['year_month'] = monthly['year_month'].astype(str)
    monthly = monthly.sort_values('year_month').reset_index(drop=True)

    return monthly


def get_category_breakdown(df: pd.DataFrame, year_month: str) -> pd.DataFrame:
    """
    Returns the sum of amounts by category for the given year_month (format: 'YYYY-MM').

    Args:
        df: A prepared DataFrame with 'date', 'category', and 'amount' columns.
        year_month: A string in the format 'YYYY-MM'. The function filters by this month.

    Returns:
        A DataFrame with columns: ['category', 'total_spend'].
        Rows are sorted by total_spend descending.
    """
    if df.empty:
        return pd.DataFrame(columns=['category', 'total_spend'])

    if 'date' not in df.columns or 'amount' not in df.columns or 'category' not in df.columns:
        logging.warning("DataFrame is missing 'date', 'amount', or 'category'. Returning empty.")
        return pd.DataFrame(columns=['category', 'total_spend'])

    # Convert year_month to a Period type for filtering
    try:
        target_period = pd.Period(year_month)
    except ValueError:
        logging.warning(f"Invalid year_month format: {year_month}. Use 'YYYY-MM'. Returning empty.")
        return pd.DataFrame(columns=['category', 'total_spend'])

    # Filter the DataFrame to only that month
    df_month = df[df['date'].dt.to_period('M') == target_period]
    if df_month.empty:
        return pd.DataFrame(columns=['category', 'total_spend'])

    breakdown = df_month.groupby('category')['amount'].sum().reset_index()
    breakdown.rename(columns={'amount': 'total_spend'}, inplace=True)
    breakdown.sort_values('total_spend', ascending=False, inplace=True)
    breakdown.reset_index(drop=True, inplace=True)

    return breakdown


def get_expenses_summary(years_back: int = 5) -> pd.DataFrame:
    """
    A convenience function that:
      1) Loads transactions from the DB
      2) Prepares the DataFrame for analysis (filtering out categories like Transfers/Income)
      3) Returns monthly expenses for the last 'years_back' years

    Args:
        years_back: How many years of data to keep.

    Returns:
        A DataFrame with ['year_month', 'total_spend'] for each month in the range.
    """
    df_raw = load_transactions()
    df_prep = prepare_expenses_dataframe(df_raw, years_back=years_back)
    return get_monthly_expenses(df_prep)


def example_usage():
    """
    A simple demonstration of how you might use these functions together.
    This is not called automatically; you can remove or adapt it for your application.
    """
    # Load raw transactions from the DB
    df_all = load_transactions()
    # Filter for last 5 years, excluding Income/Transfers/etc.
    df_expenses = prepare_expenses_dataframe(df_all, years_back=5)

    # Get monthly expense summary
    monthly_df = get_monthly_expenses(df_expenses)
    print("Monthly Expense Summary (Last 5 Years):")
    print(monthly_df)

    # Pick a specific month, e.g. '2023-08', and get category breakdown
    cat_breakdown = get_category_breakdown(df_expenses, '2023-08')
    print("\nCategory Breakdown for 2023-08:")
    print(cat_breakdown)
