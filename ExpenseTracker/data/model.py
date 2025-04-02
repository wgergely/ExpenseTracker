"""
MonthlyExpenseModel Module

This module provides the MonthlyExpenseModel, a QAbstractTableModel for displaying
monthly expense data per category with a summary row. The model now works with the
new data structure from the data module, which returns a pandas DataFrame with
columns 'category', 'total', and 'transactions'. Display labels for "category" and "amount"
are derived from the ledger.json "data_header_mapping" configuration.
"""

import logging
import math
from typing import Any, Dict

import pandas as pd
from PySide6 import QtCore

from .data import get_monthly_expenses
from ..database.database import load_config, get_cached_data

# Custom roles
TransactionsRole = QtCore.Qt.UserRole + 1
MaximumRole = QtCore.Qt.UserRole + 2
MinimumRole = QtCore.Qt.UserRole + 3
AverageRole = QtCore.Qt.UserRole + 4


class MonthlyExpenseModel(QtCore.QAbstractTableModel):
    """
    MonthlyExpenseModel provides a table model for monthly expense data per category.
    It displays, for a given target month, each expense category with its total and
    a detailed list of transactions. A summary string is provided via tooltips.
    """

    def __init__(self, year_month: str, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.setObjectName('MonthlyExpenseModel')
        self.year_month: str = year_month
        # The data_df DataFrame will have columns: 'category', 'total', 'transactions'
        self.data_df: pd.DataFrame = pd.DataFrame(columns=['category', 'total', 'transactions'])
        self._transactions_mapping: Dict[Any, Any] = {}
        self._summary_cache: Dict[Any, str] = {}
        self._metadata: Dict[str, float] = {
            'category_minimum': 0.0,
            'category_maximum': 0.0,
            'category_average': 0.0,
            'num_categories': 0,
            'num_accounts': 0,
            'num_transactions': 0,
        }
        self.refresh_data()

    @QtCore.Slot()
    def refresh_data(self) -> None:
        self.beginResetModel()
        self._reset_metadata()
        try:
            self._load_data()
        except Exception as ex:
            logging.error(f'Failed to load transactions data: {ex}')
            raise
        finally:
            self.endResetModel()

    def _reset_metadata(self) -> None:
        self._metadata = {
            'category_minimum': 0.0,
            'category_maximum': 0.0,
            'category_average': 0.0,
            'num_categories': 0,
            'num_accounts': 0,
            'num_transactions': 0,
        }

    def _load_data(self) -> None:
        # Retrieve the breakdown DataFrame for the target month using the new data API.
        breakdown = get_monthly_expenses(self.year_month)
        # Optionally add a total row aggregating all categories.
        if not breakdown.empty:
            overall_total = breakdown['total'].sum()
            # Aggregate transactions from all categories (excluding any existing 'Total' row).
            all_trans = []
            for _, row in breakdown.iterrows():
                if row['category'].strip().lower() != 'total':
                    all_trans.extend(row['transactions'])
            total_row = pd.DataFrame({
                'category': ['Total'],
                'total': [overall_total],
                'transactions': [all_trans]
            })
            breakdown = pd.concat([breakdown, total_row], ignore_index=True)
        self.data_df = breakdown

        # Build a mapping from category to its list of transactions.
        self._transactions_mapping = {}
        for _, row in self.data_df.iterrows():
            cat = row['category']
            self._transactions_mapping[cat] = row['transactions']

        self._summary_cache.clear()
        self.layoutChanged.emit()

    def _get_summary(self, category: Any) -> str:
        if category in self._summary_cache:
            return self._summary_cache[category]

        # For the "Total" row, aggregate transactions from all non-total categories.
        if isinstance(category, str) and category.strip().lower() == 'total':
            trans = []
            for cat, txns in self._transactions_mapping.items():
                if cat.strip().lower() != 'total':
                    trans.extend(txns)
        else:
            trans = self._transactions_mapping.get(category, [])

        num_trans = len(trans)
        total_val = 0.0
        row = self.data_df[self.data_df['category'] == category]
        if not row.empty:
            total_val = row.iloc[0]['total']

        # Determine the account key using the ledger.json config.
        config = load_config()
        mapping = config.get('data_header_mapping', {})
        account_key = 'account'
        for key, val in mapping.items():
            if val.strip().lower() == 'account name':
                account_key = key
                break

        accounts = {txn.get(account_key, '') for txn in trans if txn.get(account_key, '')}
        summary = f'Transactions: {num_trans}, Total: €{total_val:.2f}, Accounts: {len(accounts)}'
        self._summary_cache[category] = summary
        return summary

    @QtCore.Slot()
    def set_year_month(self, year_month: str) -> None:
        self.year_month = year_month
        self.refresh_data()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self.data_df)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 3

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self.data_df):
            return None

        record = self.data_df.iloc[row]
        category = record['category']
        total_value = record['total']

        if role in (QtCore.Qt.ToolTipRole, QtCore.Qt.StatusTipRole):
            return self._get_summary(category)

        if col == 0:
            # Category column: use config mapping for label.
            config = load_config()
            mapping = config.get('data_header_mapping', {})
            display_label = mapping.get('category', 'Category')
            display_name = category.strip().title() if isinstance(category, str) else ''
            if role == QtCore.Qt.DisplayRole:
                return display_name
            if role == QtCore.Qt.UserRole:
                return category

        elif col == 1:
            # Chart column: no display; return total in UserRole.
            if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
                return ''
            if role == QtCore.Qt.UserRole:
                return total_value

        elif col == 2:
            # Amount column: display formatted total; return raw total in UserRole.
            if role == QtCore.Qt.DisplayRole:
                return f'€{math.ceil(abs(total_value))}'
            if role == QtCore.Qt.UserRole:
                return total_value
            if role == TransactionsRole:
                return self._transactions_mapping.get(category, [])

        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> Any:
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            config = load_config()
            mapping = config.get('data_header_mapping', {})
            if section == 0:
                return mapping.get('category', 'Category')
            elif section == 1:
                return 'Chart'
            elif section == 2:
                return mapping.get('amount', 'Amount')
        return None


class TransactionsModel(QtCore.QAbstractTableModel):
    """
    TransactionsModel displays transaction data as table rows and columns.
    The header names are derived from the transaction DataFrame columns, which are
    renamed based on the ledger.json "data_header_mapping" configuration.
    """

    def __init__(self, df: pd.DataFrame = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        if df is None:
            # Load the raw transaction data from the cache.
            df = get_cached_data()
            # Load configuration to apply header mapping.
            config = load_config()
            mapping = config.get('data_header_mapping', {})
            if mapping:
                # Build a source-to-destination renaming map: {source: destination}
                rename_map = {source: dest for dest, source in mapping.items()}
                missing_sources = [src for src in rename_map if src not in df.columns]
                if missing_sources:
                    logging.warning(
                        f"TransactionsModel: Missing source columns {missing_sources} in data."
                    )
                else:
                    df = df.rename(columns=rename_map)
        self._df = df.copy()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._df)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._df.columns)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= self.rowCount():
            return None
        value = self._df.iloc[row, col]
        if role == QtCore.Qt.DisplayRole:
            return str(value)
        elif role == QtCore.Qt.EditRole:
            return value
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> any:
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            if 0 <= section < self.columnCount():
                return self._df.columns[section]
        elif orientation == QtCore.Qt.Vertical:
            return section + 1
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
