"""
ExpenseModel Module

This module provides the ExpenseModel, a QAbstractTableModel for displaying
expense data per category over a specified period with a summary row.
The model works with the new data structure from the data module, which returns a
pandas DataFrame with columns 'category', 'total', and 'transactions'. Display labels
for "category" and "amount" are derived from the ledger.json "data_header_mapping" configuration.
"""

import logging
import math
from typing import Any

import pandas as pd
from PySide6 import QtCore

from .data import get_monthly_expenses
from ..ui import ui
from ..ui.actions import signals
from ..settings import lib


# Custom roles
TransactionsRole = QtCore.Qt.UserRole + 1
MaximumRole = QtCore.Qt.UserRole + 2
MinimumRole = QtCore.Qt.UserRole + 3
AverageRole = QtCore.Qt.UserRole + 4
TotalRole = QtCore.Qt.UserRole + 5
RateRole = QtCore.Qt.UserRole + 6


class ExpenseModel(QtCore.QAbstractTableModel):
    """
    ExpenseModel provides a table model for expense data per category.
    It displays, for a given target month and span, each expense category with its total and
    a detailed list of transactions. A summary string is provided via tooltips.

    Attributes:
        columns (list): The table columns.
        year_month (str): The starting target month in 'YYYY-MM' format.
        span (int): The number of months to include, starting from year_month.
    """
    columns = ['Category', 'Chart', 'Amount']

    def __init__(self, year_month: str, span: int = 1, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent=parent)

        self.year_month: str = year_month
        self.span: int = span

        self.data_df: pd.DataFrame = pd.DataFrame(columns=self.columns)

        self.setObjectName('ExpenseModel')

        self.init_data()

        self._connect_signals()

    def _connect_signals(self) -> None:
        signals.dataAboutToBeFetched.connect(self.clear_data)
        signals.dataRangeChanged.connect(self.on_range_changed)
        signals.dataFetched.connect(self.init_data)

    def _load_data(self) -> None:
        # Retrieve the breakdown DataFrame for the target period using the new data API.
        breakdown = get_monthly_expenses(self.year_month, span=self.span)
        # Optionally add a total row aggregating all categories.
        if not breakdown.empty:
            overall_total = breakdown['total'].sum()
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

        self.layoutChanged.emit()

    def _get_trans_df(self, row: int) -> pd.DataFrame:
        try:
            trans_df = pd.DataFrame(self.data_df.iloc[row]['transactions'])
        except:
            trans_df = pd.DataFrame()

        return trans_df

    def _get_summary(self, row: int) -> str:
        trans_df = self._get_trans_df(row)

        category = trans_df.get('category', pd.Series()).unique()
        category = ', '.join(category)

        total = trans_df.get('amount', pd.Series()).sum()
        total = f'€{abs(total):.2f}'

        largest_transactions = trans_df.nsmallest(3, 'amount')
        largest_transactions = ', '.join(
            [f'€{abs(row["amount"]):.2f} ({row["description"]})\n\n' for _, row in largest_transactions.iterrows()]
        )

        accounts = trans_df.get('account', pd.Series()).unique()
        accounts = ', '.join(accounts)

        return (f'Category: {category}\n'
                f'Total: {total}\n'
                f'Accounts: {accounts}\n\n'
                f'Transactions:\n\n{largest_transactions}...'
                )

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self.data_df)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 3

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        if row < 0 or row >= self.data_df.shape[0]:
            return None

        record = self.data_df.iloc[row]
        category = record['category']
        total_value = record['total']

        df = self.data_df.iloc[:-1][['total']].abs()

        if role == TransactionsRole:
            return self._get_trans_df(row)

        if role == AverageRole:
            return df.mean().iloc[0]
        if role == MaximumRole:
            return df.max().iloc[0]
        if role == MinimumRole:
            return df.min().iloc[0]
        if role == TotalRole:
            return df.sum().iloc[0]
        if role == RateRole:
            total_value = abs(total_value)
            v = float(abs(total_value))
            _min = 0
            _max = float(df.max().iloc[0])
            v = (v - _min) / (_max - _min)
            if total_value > 0:
                v = max(v, 0.025)
            return v

        if role in (QtCore.Qt.ToolTipRole, QtCore.Qt.StatusTipRole):
            return self._get_summary(index.row())

        if role == QtCore.Qt.FontRole:
            if index.row() == self.rowCount() - 1:
                font, _ = ui.Font.BlackFont(ui.Size.MediumText(1.0))
                font.setBold(True)
                if col == 2:
                    font.setUnderline(True)
                return font

        if col == 0:
            if role == QtCore.Qt.DecorationRole:
                return ui.get_icon(category)
            if role == QtCore.Qt.DisplayRole:
                categories = lib.settings.get_section('categories')
                if not categories:
                    return category

                if category in categories:
                    display_name = categories[category]['display_name']
                else:
                    display_name = category
                return display_name

        elif col == 1:
            if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
                return ''
            if role == QtCore.Qt.UserRole:
                return total_value

        elif col == 2:
            if role == QtCore.Qt.DisplayRole:
                return f'€{math.ceil(abs(total_value))}'
            if role == QtCore.Qt.UserRole:
                return total_value

        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> Any:
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            mapping = lib.settings.get_section('data_header_mapping')
            if not mapping:
                return None

            if section == 0:
                return mapping.get('category', 'Category')
            elif section == 1:
                return 'Chart'
            elif section == 2:
                return mapping.get('amount', 'Amount')
        return None

    @QtCore.Slot()
    def init_data(self) -> None:
        self.beginResetModel()
        try:
            self._load_data()
        except Exception as ex:
            logging.error(f'Failed to load transactions data: {ex}')
            raise
        finally:
            self.endResetModel()

    @QtCore.Slot()
    def clear_data(self) -> None:
        """
        Clear the model data and reset the DataFrame.
        """
        self.beginResetModel()
        self.data_df = pd.DataFrame(columns=self.columns)
        self.endResetModel()

    @QtCore.Slot()
    def set_year_month(self, year_month: str) -> None:
        self.year_month = year_month
        self.init_data()

    @QtCore.Slot()
    def set_span(self, span: int) -> None:
        self.span = span
        self.init_data()

    @QtCore.Slot(str)
    @QtCore.Slot(int)
    def on_range_changed(self, year_month: str, span: int) -> None:
        """
        Slot to handle range changes.
        """
        self.year_month = year_month
        self.span = span

        self.init_data()


class TransactionsModel(QtCore.QAbstractTableModel):
    """
    TransactionsModel displays transaction data as table rows and columns.
    The header names are derived from the transaction DataFrame columns, which are
    renamed based on the ledger.json "data_header_mapping" configuration.
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent=parent)

        self.data_df: pd.DataFrame = pd.DataFrame(columns=['date', 'amount', 'description', 'category'])

        self._connect_signals()

        QtCore.QTimer.singleShot(1, self.init_data)

    def _connect_signals(self) -> None:
        signals.dataFetched.connect(self.init_data)
        signals.dataRangeChanged.connect(self.init_data)

        signals.authenticateRequested.connect(self.clear_data)
        signals.deauthenticateRequested.connect(self.clear_data)
        signals.dataAboutToBeFetched.connect(self.clear_data)

        signals.categorySelectionChanged.connect(self.init_data)

    def _load_data(self) -> None:
        # Get index from the main widget'
        from .. import ui
        index = ui.index()

        if not index.isValid():
            logging.warning('TransactionsModel: Invalid index.')
            self.data_df = pd.DataFrame(columns=['date', 'amount', 'description', 'category'])
            return

        df = index.data(TransactionsRole)

        if df.empty:
            logging.warning('TransactionsModel: No data available.')
            self.data_df = pd.DataFrame(columns=['date', 'amount', 'description', 'category'])
            return

        mapping = lib.settings.get_section('data_header_mapping')
        if mapping:
            rename_map = {source: dest for dest, source in mapping.items()}
            missing_sources = [src for src in rename_map if src not in df.columns]
            if missing_sources:
                logging.warning(
                    f'TransactionsModel: Missing source columns {missing_sources} in data.'
                )
            else:
                df = df.rename(columns=rename_map)

        # Sort by amount from largest absolute to smallest (descending by absolute value).
        # We'll do final sort logic in the proxy; here keep as-is ascending for raw.
        df = df.sort_values(by='amount', ascending=True)
        self.data_df = df.copy()

    @QtCore.Slot()
    def init_data(self):
        try:
            self.beginResetModel()
            self._load_data()
        except Exception as ex:
            logging.error(f'Failed to load transactions data: {ex}')
            self.data_df = pd.DataFrame(columns=['date', 'amount', 'description', 'category'])
        finally:
            self.endResetModel()

    @QtCore.Slot()
    def clear_data(self) -> None:
        """
        Clear the model data and reset the DataFrame.
        """
        self.beginResetModel()
        self.data_df = None
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if self.data_df is None:
            return 0
        return len(self.data_df)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if self.data_df is None:
            return 0
        return len(self.data_df.columns)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if self.data_df is None:
            return None
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= self.rowCount():
            return None
        value = self.data_df.iloc[row, col]

        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                if isinstance(value, pd.Timestamp):
                    return value.strftime('%d/%m/%Y')
                else:
                    return f'{value}'
            elif col == 1:
                if isinstance(value, float):
                    return f'€{abs(value):.2f}'
                elif isinstance(value, int):
                    return f'€{abs(value)}.00'
                else:
                    return f'{value}'
            elif col == 2:
                if isinstance(value, str):
                    lines = value.split('\n')
                    first_line = lines[0]
                    other_lines = lines[1:] if len(lines) > 1 else []
                    other_lines = [line.strip() for line in other_lines if line.strip()]
                    if other_lines:
                        other_lines = f', '.join(other_lines)
                    else:
                        other_lines = ''
                    return f'{first_line}\n{other_lines}'
                else:
                    return f'{value}'
            elif col == 3:
                categories = lib.settings.get_section('categories')
                if not categories:
                    return f'{value}'

                if value in categories:
                    display_name = categories[value]['display_name']
                else:
                    display_name = f'{value}'
                return display_name
            else:
                return f'{value}'

        elif role == QtCore.Qt.DecorationRole:
            if col == 3:
                return ui.get_icon(value)

        elif role == QtCore.Qt.FontRole:
            if index.column() == 0:
                font, _ = ui.Font.ThinFont(ui.Size.SmallText(1.0))
                font.setBold(False)
                return font
            if index.column() == 2:
                font, _ = ui.Font.MediumFont(ui.Size.SmallText(1.0))
                return font

        elif role == QtCore.Qt.EditRole:
            return value
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> Any:
        if self.data_df is None:
            return None
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            if 0 <= section < self.columnCount():
                return self.data_df.columns[section].title()
        elif orientation == QtCore.Qt.Vertical:
            return section + 1
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable


class ExpenseSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Sort/Filter proxy for ExpenseModel.
    Allows sorting by either Category (column 0) or Amount (column 2).
    For filtering, not used by default, but can be extended.
    """
    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        if left.column() == 2 and right.column() == 2:
            # Sort by absolute numeric value
            left_data = abs(left.model().data(left, QtCore.Qt.UserRole) or 0)
            right_data = abs(right.model().data(right, QtCore.Qt.UserRole) or 0)
            return left_data < right_data
        return super().lessThan(left, right)


class TransactionsSortFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Sort/Filter proxy for TransactionsModel.
    Sorts by absolute amount for column 1. Allows text filtering on description (column 2).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDynamicSortFilter(True)
        # By default, filter on the description column (2).
        self.setFilterKeyColumn(2)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        if left.column() == 1 and right.column() == 1:
            left_val = left.model().data(left, QtCore.Qt.EditRole)
            right_val = right.model().data(right, QtCore.Qt.EditRole)
            left_abs = abs(left_val) if isinstance(left_val, (int, float)) else 0
            right_abs = abs(right_val) if isinstance(right_val, (int, float)) else 0
            return left_abs < right_abs
        return super().lessThan(left, right)
