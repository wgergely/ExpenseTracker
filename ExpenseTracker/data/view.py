"""
MonthlyExpenseView Module

This module provides a custom QTableView (MonthlyExpenseView) for displaying monthly expense data
with a chart-like appearance. Double-clicking any row opens a popup dialog that displays the
transaction data for the selected category using the bespoke TransactionsModel and TransactionsView.
"""

import logging

import pandas as pd
from PySide6 import QtCore, QtWidgets, QtGui

from .model import ExpenseModel
from .model import RateRole
from .model import TransactionsModel
from ..ui import ui


class GraphDelegate(QtWidgets.QStyledItemDelegate):
    """
    A custom delegate to draw a simple bar chart for the chart column.
    """

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        super().paint(painter, option, index)

        if index.column() != 1:
            return

        if index.row() == index.model().rowCount() - 1:
            return

        selected = option.state & QtWidgets.QStyle.State_Selected
        hover = option.state & QtWidgets.QStyle.State_MouseOver

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        rect = QtCore.QRectF(option.rect)
        offset = ui.Size.Indicator(0.8)

        rect = rect.adjusted(
            offset,
            offset,
            -offset,
            -offset
        )

        center = rect.center()

        if selected or hover:
            rect.setHeight(ui.Size.Margin(0.6))
        else:
            rect.setHeight(ui.Size.Margin(0.5))

        rect.moveCenter(center)

        gradient = QtGui.QLinearGradient(
            rect.topLeft(),
            rect.topRight()
        )
        gradient.setColorAt(0.0, ui.Color.Green())
        gradient.setColorAt(1.0, ui.Color.LightRed())

        # Calculate
        width = float(rect.width()) * index.data(RateRole)
        width = max(width, ui.Size.Separator(1.0)) if index.data(RateRole) > 0.0 else width
        rect.setWidth(width)

        painter.setBrush(gradient)
        pen = QtCore.Qt.NoPen

        painter.setPen(pen)

        if hover or selected:
            o = ui.Size.Separator(5.0)
        else:
            o = ui.Size.Separator(3.0)
        painter.drawRoundedRect(
            rect,
            o,
            o
        )


class MonthlyExpenseView(QtWidgets.QTableView):
    """
    MonthlyExpenseView is a custom QTableView for displaying monthly expense data.

    It hides headers, enforces single row selection, and uses custom delegates for a
    chart-like appearance. A double-click on any row opens a popup dialog displaying the
    transactions for the selected category using the bespoke transactions model/view.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self.horizontalHeader().hide()
        self.verticalHeader().hide()

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Expanding
        )

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        self.setShowGrid(False)
        self.setAlternatingRowColors(False)

        self.setWordWrap(True)
        self.setTextElideMode(QtCore.Qt.ElideRight)

        ui.set_stylesheet(self)

        self._init_delegates()
        self._connect_signals()

    def _init_delegates(self) -> None:
        self.setItemDelegate(GraphDelegate(self))

    def _connect_signals(self) -> None:
        self.doubleClicked.connect(self.handle_double_click)

    def setModel(self, model):
        if not isinstance(model, ExpenseModel):
            raise TypeError("Expected a ExpenseModel instance.")
        super().setModel(model)
        self._init_section_sizing()

    def _init_section_sizing(self) -> None:
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)

        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.4))

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(480, 120)

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

        model = TransactionsModel(df_transactions)

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Transactions")
        dialog.setMinimumSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )

        QtWidgets.QVBoxLayout(dialog)
        o = ui.Size.Margin(1.0)
        dialog.layout().setContentsMargins(o, o, o, o)

        view = TransactionsView(dialog)
        view.setModel(model)
        dialog.layout().addWidget(view)

        dialog.open()


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
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)

        self.setShowGrid(True)
        self.setAlternatingRowColors(False)

        self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)

    def sizeHint(self) -> QtCore.QSize:
        """Returns the preferred size for the view."""
        return QtCore.QSize(800, 400)

    def _init_header(self) -> None:
        """Initializes the header properties."""
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)

        # Set sorting enabled for the first column
        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, QtCore.Qt.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)

        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.8))
        header.setHidden(True)

    def setModel(self, model: TransactionsModel) -> None:
        """Sets the model for the view and initializes the header."""
        if not isinstance(model, TransactionsModel):
            raise TypeError("Expected a TransactionsModel instance.")
        super().setModel(model)
        self._init_header()
