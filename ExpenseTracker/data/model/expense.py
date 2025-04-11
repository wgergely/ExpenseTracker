import enum
import logging
from typing import Any

import pandas as pd
from PySide6 import QtCore, QtGui

from ..data import get_data
from ...settings import lib
from ...settings import locale
from ...ui import ui
from ...ui.actions import signals



TransactionsRole = QtCore.Qt.UserRole + 1
MaximumRole = QtCore.Qt.UserRole + 2
MinimumRole = QtCore.Qt.UserRole + 3
AverageRole = QtCore.Qt.UserRole + 4
TotalRole = QtCore.Qt.UserRole + 5
WeightRole = QtCore.Qt.UserRole + 6



class Columns(enum.IntEnum):
    Icon = enum.auto()
    Category = enum.auto()
    Weight = enum.auto()
    Amount = enum.auto()


class ExpenseModel(QtCore.QAbstractTableModel):
    header = ['', 'Category', '', 'Amount']

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
            df = get_data()
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
