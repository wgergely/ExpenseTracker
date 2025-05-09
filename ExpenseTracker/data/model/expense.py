import enum
import logging
from typing import Any, Optional

import pandas as pd
from PySide6 import QtCore, QtGui

from ..data import get_data, SummaryMode
from ...core.sync import sync
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
CategoryRole = QtCore.Qt.UserRole + 7


class Columns(enum.IntEnum):
    """Column indices for the ExpenseModel table."""
    Icon = 0
    Category = 1
    Weight = 2
    Amount = 3


class ExpenseModel(QtCore.QAbstractTableModel):
    """Table model for displaying expense summaries."""

    HEADERS = {
        Columns.Icon.value: '',
        Columns.Category.value: 'Category',
        Columns.Weight.value: '',
        Columns.Amount.value: 'Amount'
    }
    MIME_INTERNAL = 'application/vnd.text.list'

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
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
        signals.presetAboutToBeActivated.connect(self.clear_data)
        signals.dataAboutToBeFetched.connect(self.clear_data)
        signals.dataFetched.connect(self.init_data)
        signals.categoryExcluded.connect(self.init_data)

        @QtCore.Slot(str, object)
        def metadata_changed(key: str, value: object) -> None:
            if key in (
                    'hide_empty_categories',
                    'exclude_negative',
                    'exclude_zero',
                    'exclude_positive',
                    'summary_mode',
                    'span',
                    'yearmonth'
            ):
                self.init_data()

        signals.metadataChanged.connect(metadata_changed)
        sync.dataUpdated.connect(self.init_data)

        signals.categoryAdded.connect(self.init_data)
        signals.categoryRemoved.connect(self.init_data)
        signals.categoryOrderChanged.connect(self.init_data)

        signals.initializationRequested.connect(self.init_data)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._df)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self.HEADERS)

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

        if role == CategoryRole:
            return category

        # Custom roles for aggregated stats
        if role == TransactionsRole:
            if is_total_row:
                # return all transactions
                all_transactions = []
                for i in range(self.rowCount()):
                    try:
                        all_transactions += self._cache['transactions'][i]
                    except Exception as ex:
                        logging.debug(f'Error fetching transactions for row {i}: {ex}')
                return all_transactions
            else:
                if not transactions:
                    return []
                if not isinstance(transactions, list):
                    return []
                return transactions
        if role == AverageRole:
            return self._cache['mean'][row]
        if role == MaximumRole:
            return self._cache['max'][row]
        if role == MinimumRole:
            return self._cache['min'][row]
        if role == TotalRole:
            return total_value
        if role == WeightRole:
            return weight_value

        if role in (QtCore.Qt.ToolTipRole, QtCore.Qt.StatusTipRole):
            return description_value

        if role == QtCore.Qt.FontRole:
            if total_value == 0:
                font, _ = ui.Font.ThinFont(ui.Size.MediumText(1.0))
                return font
            if is_total_row:
                font, _ = ui.Font.BlackFont(ui.Size.MediumText(1.0))
                font.setBold(True)
                return font

        if col == Columns.Icon:
            if role == QtCore.Qt.DecorationRole:
                # no icon for the "Total" row
                if index.data(QtCore.Qt.DisplayRole) == 'Total':
                    return None

                if category == '':
                    return ui.get_icon('cat_unknown', color=ui.Color.Yellow(), engine=ui.CategoryIconEngine)

                config = lib.settings.get_section('categories')
                if not config:
                    return None

                category = self._cache['category'][row]
                if category not in config:
                    return None

                icon_name = config[category].get('icon', 'cat_unclassified')
                hex_color = config[category].get('color', ui.Color.Text().name(QtGui.QColor.HexRgb))
                color = QtGui.QColor(hex_color)

                icon = ui.get_icon(icon_name, color=color, engine=ui.CategoryIconEngine)
                return icon

        # Handle columns
        if col == Columns.Category:
            if role == QtCore.Qt.DisplayRole:
                if is_total_row:
                    if lib.settings['summary_mode'] == SummaryMode.Total.value:
                        return 'Total'
                    elif lib.settings['summary_mode'] == SummaryMode.Monthly.value:
                        return 'Monthly Average'
                    return 'Total*'

                if category == '':
                    return '(Uncategorized)'

                categories_cfg = lib.settings.get_section('categories')
                if not categories_cfg:
                    return category

                if category in categories_cfg and categories_cfg[category].get('display_name'):
                    return categories_cfg[category]['display_name']

                return category
            if role == QtCore.Qt.FontRole:
                font, _ = ui.Font.ThinFont(ui.Size.MediumText(1.0))
                font.setWeight(QtGui.QFont.Bold)
                return font
            if role == QtCore.Qt.ForegroundRole:
                if total_value == 0:
                    return ui.Color.DisabledText()

                if category == '':
                    return ui.Color.Yellow()

            if role == QtCore.Qt.DecorationRole:
                config = lib.settings.get_section('categories')
                if is_total_row:
                    return None
                if category and category not in config:
                    return ui.get_icon('btn_alert', color=ui.Color.Yellow)
                return None

        elif col == Columns.Weight:
            return None

        elif col == Columns.Amount:
            # Amount column
            if role == QtCore.Qt.DisplayRole:
                return locale.format_currency_value(int(total_value), lib.settings['locale'])
            if role == QtCore.Qt.FontRole:
                if total_value == 0:
                    font, _ = ui.Font.ThinFont(ui.Size.MediumText(1.0))
                    return font
                font, _ = ui.Font.BoldFont(ui.Size.MediumText(1.0))
                font.setWeight(QtGui.QFont.Bold)
                return font
            if role == QtCore.Qt.TextAlignmentRole:
                return QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter

        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole) -> Any:
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.HEADERS.get(section, '')
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsDropEnabled
        base_flags = super().flags(index)
        flags = (base_flags
                 | QtCore.Qt.ItemIsEnabled
                 | QtCore.Qt.ItemIsSelectable)
        if index.column() == Columns.Icon:
            flags |= QtCore.Qt.ItemIsEditable
        return flags

    @QtCore.Slot()
    def _init_data(self):
        df = get_data()

        if df is None or df.empty:
            logging.debug('No data available')
            self._df = pd.DataFrame(columns=lib.EXPENSE_DATA_COLUMNS)
            return

        self._df = df.reset_index(drop=True)

        for k in lib.EXPENSE_DATA_COLUMNS:
            self._cache[k] = self._df[k].tolist()

        # if last row is a "Total" row, exclude it from stats
        if len(self._df) > 1 and self._df.iloc[-1]['category'] == 'Total':
            core_df = self._df.iloc[:-1]
        else:
            core_df = self._df

        self._cache['mean'] = core_df['total'].mean()
        self._cache['max'] = core_df['total'].max()
        self._cache['min'] = core_df['total'].min()

        self._cache['mean'] = [self._cache['mean']] * len(self._df)
        self._cache['max'] = [self._cache['max']] * len(self._df)
        self._cache['min'] = [self._cache['min']] * len(self._df)

    @QtCore.Slot()
    def init_data(self) -> None:
        logging.debug('Initializing model data')
        self.beginResetModel()

        try:
            self._init_data()
        except Exception as ex:
            logging.error(f'Failed to load transactions data: {ex}')
            self._df = pd.DataFrame(columns=lib.EXPENSE_DATA_COLUMNS)
        finally:
            self.endResetModel()

    @QtCore.Slot()
    def clear_data(self) -> None:
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
    """Sort/filter proxy model for expense summaries.

    Ensures the 'Total' row remains at the end and supports sorting by category or amount.
    """

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        # sort modes: 'config', 'category', 'amount'
        self._sort_mode = 'config'

    def sort(self, column: int, order: QtCore.Qt.SortOrder = QtCore.Qt.AscendingOrder) -> None:
        # Determine requested sort mode
        if column < 0:
            self._sort_mode = 'config'
        elif column == Columns.Category:
            self._sort_mode = 'category'
        elif column == Columns.Amount:
            self._sort_mode = 'amount'
        else:
            self._sort_mode = 'config'

        super().sort(column, order)

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        left_cat = left.data(CategoryRole)
        right_cat = right.data(CategoryRole)

        if left_cat == 'Total' and right_cat != 'Total':
            return False
        if right_cat == 'Total' and left_cat != 'Total':
            return True

        if self._sort_mode == 'config':
            config = lib.settings.get_section('categories')
            categories = list(config.keys())

            left_idx = categories.index(left_cat) if left_cat in categories else len(categories)
            right_idx = categories.index(right_cat) if right_cat in categories else len(categories)

            return left_idx < right_idx

        if self._sort_mode == 'category':
            return str(left_cat).lower() < str(right_cat).lower()

        if self._sort_mode == 'amount':
            left_val = left.data(TotalRole)
            right_val = right.data(TotalRole)
            try:
                return float(left_val) < float(right_val)
            except Exception:
                return False
        return super().lessThan(left, right)
