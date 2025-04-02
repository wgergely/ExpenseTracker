"""
MonthlyExpenseView Module

This module provides a custom QTableView (MonthlyExpenseView) for displaying monthly expense data
with a chart-like appearance. Double-clicking any row opens a popup dialog that displays the
transaction data for the selected category using the bespoke TransactionsModel and TransactionsView.
"""

import logging

import pandas as pd
from PySide6 import QtCore, QtWidgets, QtGui

from .model import MonthlyExpenseModel
from .model import TransactionsModel
from ..ui import ui


class AlignmentDelegate(QtWidgets.QStyledItemDelegate):
    """
    A delegate to enforce text alignment in table cells.
    """

    def __init__(self, alignment: int, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.alignment = alignment

    def initStyleOption(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:
        super().initStyleOption(option, index)
        option.displayAlignment = self.alignment


class ChartDelegate(QtWidgets.QStyledItemDelegate):
    """
    A custom delegate to draw a simple bar chart for the chart column.
    """

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        value = index.data(QtCore.Qt.UserRole)
        if value is None:
            return super().paint(painter, option, index)
        try:
            value = float(value)
        except (ValueError, TypeError):
            return super().paint(painter, option, index)
        painter.save()
        rect = option.rect.adjusted(4, 4, -4, -4)
        # Arbitrary scaling: maximum value corresponds to full width.
        max_val = 1000.0
        bar_width = int(rect.width() * min(value / max_val, 1.0))
        bar_rect = QtCore.QRect(rect.left(), rect.top(), bar_width, rect.height())
        painter.fillRect(bar_rect, option.palette.highlight())
        painter.restore()


class MonthlyExpenseView(QtWidgets.QTableView):
    """
    MonthlyExpenseView is a custom QTableView for displaying monthly expense data.

    It hides headers, enforces single row selection, and uses custom delegates for a
    chart-like appearance. A double-click on any row opens a popup dialog displaying the
    transactions for the selected category using the bespoke transactions model/view.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        # Hide headers for a cleaner look.
        self.horizontalHeader().hide()
        self.verticalHeader().hide()

        # Use standard size policies.
        self.setMinimumSize(640, 480)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # Enforce single row selection.
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)

        ui.set_stylesheet(self)

        self._init_delegates()
        self._connect_signals()

    def _init_delegates(self) -> None:
        self.setItemDelegateForColumn(0, AlignmentDelegate(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, self))
        self.setItemDelegateForColumn(1, ChartDelegate(self))
        self.setItemDelegateForColumn(2, AlignmentDelegate(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self))

    def _connect_signals(self) -> None:
        self.doubleClicked.connect(self.handle_double_click)

    def setModel(self, model):
        if not isinstance(model, MonthlyExpenseModel):
            raise TypeError("Expected a MonthlyExpenseModel instance.")
        super().setModel(model)
        self._init_section_sizing()

    def _init_section_sizing(self) -> None:
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)

    def sizeHint(self) -> QtCore.QSize:
        # Rely on standard size policies; return a default size.
        return QtCore.QSize(640, 480)

    @QtCore.Slot(QtCore.QModelIndex)
    def handle_double_click(self, index: QtCore.QModelIndex) -> None:
        """
        Slot called on double-clicking a row.
        Opens a popup dialog displaying transaction details for the selected category
        using the bespoke TransactionsModel and TransactionsView.
        """
        if not index.isValid():
            return

        model = self.model()
        row = index.row()

        # Extract transactions for the selected category from the model's data.
        try:
            transactions = model.data_df.iloc[row]['transactions']
        except (IndexError, KeyError) as ex:
            logging.error(f"Error retrieving transactions for row {row}: {ex}")
            return

        if not transactions:
            return

        # Create a DataFrame from the list of transaction dictionaries.
        df_transactions = pd.DataFrame(transactions)
        if df_transactions.empty:
            return

        # Create a new TransactionsModel using the transaction DataFrame.
        tx_model = TransactionsModel(df_transactions)

        # Create and configure the popup dialog.
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Transactions")
        dialog.setMinimumSize(800, 600)
        layout = QtWidgets.QVBoxLayout(dialog)

        # Create a TransactionsView and set its model.
        tx_view = TransactionsView(dialog)
        tx_view.setModel(tx_model)
        layout.addWidget(tx_view)

        dialog.exec()


class TransactionsView(QtWidgets.QTableView):
    """
    TransactionsView is a custom QTableView for displaying transaction data.
    It is tailored for the TransactionsModel, configuring selection, sizing, and header behavior
    for an optimal, dynamic display of the transactions table.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self._init_view()

    def _init_view(self) -> None:
        """Initializes view properties and layout."""
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setShowGrid(True)
        self.setMinimumSize(640, 480)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def sizeHint(self) -> QtCore.QSize:
        """Returns the preferred size for the view."""
        return QtCore.QSize(800, 600)
