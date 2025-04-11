"""
ExpenseModel Module

This module provides the ExpenseModel, a QAbstractTableModel for displaying
expense data per category over a specified period with a summary row.
The model works with the new data structure from the data module, which returns a
pandas DataFrame with columns 'category', 'total', and 'transactions'. Display labels
for "category" and "amount" are derived from the ledger.json "mapping" configuration.
"""

import logging
from typing import Any

import pandas as pd
from PySide6 import QtCore, QtGui

from ..settings import lib
from ..settings import locale
from ..ui import ui
from ..ui.actions import signals

# Custom roles
TransactionsRole = QtCore.Qt.UserRole + 1
MaximumRole = QtCore.Qt.UserRole + 2
MinimumRole = QtCore.Qt.UserRole + 3
AverageRole = QtCore.Qt.UserRole + 4
TotalRole = QtCore.Qt.UserRole + 5
WeightRole = QtCore.Qt.UserRole + 6


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
    header = ['Category', '', 'Amount']

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent=parent)
        self.setObjectName('ExpenseTrackerExpenseModel')

        self._df: pd.DataFrame = pd.DataFrame(columns=lib.EXPENSE_DATA_COLUMNS)

        self._cache = {
            'category': [],
            'total': [],
            'transactions': [],
            'weight': [],
            'description': [],
            'mean': 0,
            'max': 0,
            'min': 0,
        }

        self._connect_signals()

    def _connect_signals(self) -> None:
        signals.dataAboutToBeFetched.connect(self.clear_data)

        signals.dataFetched.connect(self.init_data)
        signals.dataRangeChanged.connect(self.init_data)
        signals.configSectionChanged.connect(self.init_data)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._df)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 3

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()

        if row < 0 or row >= self.rowCount():
            return None

        # Grab cached values
        category = self._cache['category'][row]
        total_value = self._cache['total'][row]
        weight_value = self._cache['weight'][row]
        description_value = self._cache['description'][row]
        transactions = self._cache['transactions'][row]

        # Determine if this row is the special “Total” row
        is_total_row = (category == 'Total' and row == self.rowCount() - 1)

        # Custom roles for aggregated stats
        if role == TransactionsRole:
            # Return a copy if you don’t want the caller modifying your cache in-place
            return list(transactions)
        if role == AverageRole:
            return self._cache['mean']
        if role == MaximumRole:
            return self._cache['max']
        if role == MinimumRole:
            return self._cache['min']
        if role == TotalRole:
            return total_value
        if role == WeightRole:
            return weight_value

        # Tooltip and status tips
        if role in (QtCore.Qt.ToolTipRole, QtCore.Qt.StatusTipRole):
            return description_value

        # Bold/underline font for “Total” row (optional)
        if role == QtCore.Qt.FontRole:
            if is_total_row:
                font, _ = ui.Font.BlackFont(ui.Size.MediumText(1.0))
                font.setBold(True)
                return font

        # Handle columns
        if col == 0:
            # Icon or DisplayName
            if role == QtCore.Qt.DecorationRole:
                return ui.get_icon(category)
            if role == QtCore.Qt.DisplayRole:
                categories_cfg = lib.settings.get_section('categories')
                if not categories_cfg:
                    return category
                # Use a display name if present
                if category in categories_cfg and categories_cfg[category].get('display_name'):
                    return categories_cfg[category]['display_name']
                return category
            if role == QtCore.Qt.FontRole:
                font, _ = ui.Font.ThinFont(ui.Size.MediumText(1.0))
                font.setWeight(QtGui.QFont.Bold)
                return font

        elif col == 1:
            # Typically an empty or “notes” column
            if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
                return ''

        elif col == 2:
            # Amount column
            if role == QtCore.Qt.DisplayRole:
                return locale.format_currency_value(int(total_value), lib.settings['locale'])
            if role == QtCore.Qt.FontRole:
                # Make amounts bold
                font, _ = ui.Font.BlackFont(ui.Size.MediumText(1.0))
                font.setWeight(QtGui.QFont.Black)
                return font
            if role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter

        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> Any:
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.header[section]
        return None

    @QtCore.Slot()
    def init_data(self) -> None:
        logging.debug('Initializing model data')
        self.beginResetModel()
        try:
            from ..data import data
            df = data.get_data()
            self._df = df.reset_index(drop=True)

            for k in lib.EXPENSE_DATA_COLUMNS:
                self._cache[k] = self._df[k].tolist()

            #    If your last row is a "Total" row, exclude it from stats
            if len(self._df) > 1 and self._df.iloc[-1]['category'] == 'Total':
                core_df = self._df.iloc[:-1]
            else:
                core_df = self._df

            self._cache['mean'] = core_df['total'].mean()
            self._cache['max'] = core_df['total'].max()
            self._cache['min'] = core_df['total'].min()

        except Exception as ex:
            logging.error(f'Failed to load transactions data: {ex}')
            self._df = pd.DataFrame(columns=lib.EXPENSE_DATA_COLUMNS)
            raise
        finally:
            self.endResetModel()

    @QtCore.Slot()
    def clear_data(self) -> None:
        """
        Clear the model data and reset the DataFrame.
        """
        logging.debug('Clearing model data')

        self.beginResetModel()

        self._cache = {
            'category': [],
            'total': [],
            'transactions': [],
            'weight': [],
            'description': [],
            'mean': 0,
            'max': 0,
            'min': 0,
        }
        self._df = pd.DataFrame(columns=lib.EXPENSE_DATA_COLUMNS)

        self.endResetModel()


class TransactionsModel(QtCore.QAbstractTableModel):
    """
    TransactionsModel displays transaction data as table rows and columns.
    The header names are derived from the transaction DataFrame columns, which are
    renamed based on the ledger.json "mapping" configuration.
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent=parent)

        self._df: pd.DataFrame = pd.DataFrame(columns=lib.TRANSACTION_DATA_COLUMNS)

        self._connect_signals()

        QtCore.QTimer.singleShot(1, self.init_data)

    def _connect_signals(self) -> None:
        signals.dataAboutToBeFetched.connect(self.clear_data)
        signals.dataFetched.connect(self.init_data)
        signals.dataRangeChanged.connect(self.init_data)

        signals.configSectionChanged.connect(self.init_data)
        signals.categorySelectionChanged.connect(self.init_data)

    def _load_data(self) -> None:
        from .. import ui
        index = ui.index()

        if not index.isValid():
            self._df = pd.DataFrame(columns=lib.TRANSACTION_DATA_COLUMNS)
            return

        df = index.data(TransactionsRole)

        if df.empty:
            logging.warning('TransactionsModel: No data available.')
            self._df = pd.DataFrame(columns=lib.TRANSACTION_DATA_COLUMNS)
            return

        df = df.sort_values(by='amount', ascending=True)
        self._df = df.copy()

    @QtCore.Slot()
    def init_data(self):
        try:
            self.beginResetModel()
            self._load_data()
        except Exception as ex:
            logging.error(f'Failed to load transactions data: {ex}')
            self._df = pd.DataFrame(columns=lib.TRANSACTION_DATA_COLUMNS)
        finally:
            self.endResetModel()

    @QtCore.Slot()
    def clear_data(self) -> None:
        """
        Clear the model data and reset the DataFrame.
        """
        self.beginResetModel()
        self._df = None
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if self._df is None:
            return 0
        return len(self._df)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if self._df is None:
            return 0
        return len(self._df.columns)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if self._df is None:
            return None
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()

        if row < 0 or row >= self.rowCount():
            return None

        value = self._df.iloc[row, col]

        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                if isinstance(value, pd.Timestamp):
                    return value.strftime('%d/%m/%Y')
                else:
                    return f'{value}'
            elif col == 1:
                if isinstance(value, (int, float)):
                    return locale.format_currency_value(value, lib.settings['locale'])
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
                font.setWeight(QtGui.QFont.Normal)
                return font
            if index.column() == 1:
                font, _ = ui.Font.BlackFont(ui.Size.MediumText(1.0))
                font.setWeight(QtGui.QFont.Black)
                return font
            if index.column() == 2:
                font, _ = ui.Font.MediumFont(ui.Size.SmallText(1.0))
                return font

        elif role == QtCore.Qt.ForegroundRole:
            if index.column() == 1:
                if not isinstance(value, (int, float)):
                    return None
                if value < 0:
                    return ui.Color.Red()
                if value == 0:
                    return ui.Color.DisabledText()
                if value > 0:
                    return ui.Color.Green()


        elif role == QtCore.Qt.EditRole:
            return value

        elif role in (QtCore.Qt.StatusTipRole, QtCore.Qt.ToolTipRole):
            if col == 0:
                if isinstance(value, pd.Timestamp):
                    return value.strftime('%d/%m/%Y')
                else:
                    return f'{value}'
            elif col == 1:
                if isinstance(value, float):
                    return locale.format_currency_value(value, lib.settings['locale'])
                elif isinstance(value, int):
                    return locale.format_currency_value(value, lib.settings['locale'])
                else:
                    return f'{value}'
            elif col == 2:
                if isinstance(value, str):
                    return f'{value}'
            elif col == 3:
                categories = lib.settings.get_section('categories')
                if not categories:
                    return f'{value}'

                if value in categories:
                    display_name = categories[value]['display_name']
                else:
                    display_name = f'{value}'
                return f'{display_name} ({value})'

        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> Any:
        if self._df is None:
            return None
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            if 0 <= section < self.columnCount():
                return self._df.columns[section].title()
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
