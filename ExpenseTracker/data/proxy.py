# ExpensesTracker/graph/proxy.py
"""
Qt Data Visualization Proxy Utilities

"""

import logging
import pandas as pd
from typing import Optional, List
from PySide6 import QtDataVisualization

from .data import load_transactions, prepare_expenses_dataframe


def create_single_period_bar_proxy(
    year: int,
    month: int,
    average_window: int = 1,
    predefined_categories: Optional[List[str]] = None
) -> QtDataVisualization.QBarDataProxy:
    """
    Builds a QBarDataProxy showing each category's spending for a single month
    or an N-month average ending in that month.
    Args:
        year: The year of the target month, e.g. 2023.
        month: The month of the target period, 1..12.
        average_window: If 1, we show only that month. If 2, we average that
                        month + 1 prior month, etc.
        predefined_categories: If provided, we enforce that row order. Missing
                               categories get zero. Otherwise, derive categories
                               from the data, sorted alphabetically.

    Returns:
        A QBarDataProxy object with one column. Rows represent each category
        plus 'All Categories' at the end.

    Example:
        # Single month for August 2023
        proxy = create_single_period_bar_proxy(2023, 8, 1)
        # 3-month average up to August 2023
        proxy = create_single_period_bar_proxy(2023, 8, 3)

    """
    # Construct 'YYYY-MM' from the input year/month
    month_str = f'{year:04d}-{month:02d}'

    # 1) Load & prepare the ledger DataFrame
    df_raw = load_transactions()
    df_prepared = prepare_expenses_dataframe(df_raw, years_back=5)  # keep plenty data

    if df_prepared.empty:
        logging.warning('No prepared expense data available. Returning an empty QBarDataProxy.')
        return QtDataVisualization.QBarDataProxy()


    # Ensure we have columns: 'date', 'category', 'amount'
    required_cols = {'date', 'category', 'amount'}
    if not required_cols.issubset(df_prepared.columns):
        missing = required_cols - set(df_prepared.columns)
        logging.warning(f'Missing columns in prepared DataFrame: {missing}. Returning empty.')
        return QtDataVisualization.QBarDataProxy()

    # 2) Build the target period as a pandas Period
    try:
        target_period = pd.Period(month_str, freq='M')  # e.g. '2023-08'
    except ValueError:
        logging.warning(f'Invalid year/month combination: {year}-{month}. Returning empty proxy.')
        return QtDataVisualization.QBarDataProxy()

    # We'll collect (average_window) months including the target. e.g. if window=3 -> [2023-08, 2023-07, 2023-06]
    needed_periods = [target_period - i for i in range(average_window)]

    # Add a helper column for year-month
    df_prepared['__period__'] = df_prepared['date'].dt.to_period('M')

    # Filter to relevant months
    df_filtered = df_prepared[df_prepared['__period__'].isin(needed_periods)].copy()
    if df_filtered.empty:
        logging.warning('No transactions found in the requested period(s). Returning empty proxy.')
        return QtDataVisualization.QBarDataProxy()

    # 3) Group by (category, __period__), sum amounts
    grouped = (
        df_filtered
        .groupby(['category', '__period__'])['amount']
        .sum()
        .reset_index()
    )

    # Pivot => rows=category, columns=__period__, values=amount
    pivot_df = grouped.pivot(index='category', columns='__period__', values='amount').fillna(0.0)

    # Figure out final list of categories
    if predefined_categories is not None:
        categories = predefined_categories
    else:
        categories = sorted(pivot_df.index)

    # Summation or average
    cat_values = {}
    for cat in categories:
        total_sum = 0.0
        for p in needed_periods:
            if cat in pivot_df.index and p in pivot_df.columns:
                total_sum += pivot_df.loc[cat, p]
        if average_window > 1:
            cat_values[cat] = total_sum / average_window
        else:
            cat_values[cat] = total_sum

    # 'All Categories' row is the sum of all cat_values
    grand_total = sum(cat_values.values())
    cat_values['All Categories'] = grand_total

    # 4) Build QBarDataProxy
    proxy = QtDataVisualization.QBarDataProxy()

    # Row labels => categories plus 'All Categories'
    row_labels = list(categories)
    row_labels.append('All Categories')

    # Place each row's numeric value
    for i, cat in enumerate(row_labels):
        val = cat_values[cat]
        item = QtDataVisualization.QBarDataItem(val)
        proxy.addRow([item,], cat)

    # Single-month vs. multi-month label
    if average_window == 1:
        col_label = month_str
    else:
        col_label = f'{average_window}-mo avg up to {month_str}'

    proxy.setRowLabels(row_labels)
    proxy.setColumnLabels([col_label])

    n_rows = len(row_labels)

    logging.info(
        f'Created a single-column bar proxy for {month_str}, window={average_window}, '
        f'{n_rows} rows including "All Categories".'
    )

    return proxy
