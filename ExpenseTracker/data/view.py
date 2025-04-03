"""
ExpenseView Module

This module provides a custom QTableView (ExpenseView) for displaying monthly expense data
with a chart-like appearance. Double-clicking or pressing Enter on a row opens a popup dialog
displaying the transaction data for the selected category using the bespoke TransactionsModel and TransactionsView.
"""

from PySide6 import QtCore, QtWidgets, QtGui

from .model import ExpenseModel, RateRole, TransactionsModel
from ..ui import ui
from ..ui.actions import signals


class TransactionsDialog(QtWidgets.QDialog):
    """
    TransactionsDialog is a custom dialog for displaying transaction data.

    It initializes the view and sets up the layout for displaying transactions.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle('Transactions')
        self.setMinimumSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )

        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMinMaxButtonsHint)

        self.view = None

        self._create_ui()
        self._init_model()

    def _create_ui(self) -> None:
        QtWidgets.QVBoxLayout(self)
        o = ui.Size.Margin(1.0)

        self.layout().setContentsMargins(o, o, o, o)

        self.view = TransactionsView(parent=self)
        self.view.setObjectName('ExpenseTrackerTransactionsView')

        self.layout().addWidget(self.view, 1)

    def _init_model(self):
        model = TransactionsModel()
        self.view.setModel(model)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )


class GraphDelegate(QtWidgets.QStyledItemDelegate):
    """A custom delegate to draw a simple bar chart for the chart column."""

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        super().paint(painter, option, index)
        if index.column() != 1 or index.row() == index.model().rowCount() - 1:
            return

        selected = option.state & QtWidgets.QStyle.State_Selected
        hover = option.state & QtWidgets.QStyle.State_MouseOver

        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        rect = QtCore.QRectF(option.rect)
        offset = ui.Size.Indicator(0.8)
        rect = rect.adjusted(offset, offset, -offset, -offset)
        center = rect.center()

        rect.setHeight(ui.Size.Margin(0.6) if (selected or hover) else ui.Size.Margin(0.5))
        rect.moveCenter(center)

        gradient = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0.0, ui.Color.Green())
        gradient.setColorAt(1.0, ui.Color.LightRed())

        width = float(rect.width()) * index.data(RateRole)
        width = max(width, ui.Size.Separator(1.0)) if index.data(RateRole) > 0.0 else width
        rect.setWidth(width)

        painter.setBrush(gradient)
        painter.setPen(QtCore.Qt.NoPen)

        o = ui.Size.Separator(5.0) if (hover or selected) else ui.Size.Separator(3.0)
        painter.drawRoundedRect(rect, o, o)


class ExpenseView(QtWidgets.QTableView):
    """
    ExpenseView is a custom QTableView for displaying monthly expense data.

    Double-clicking or pressing Enter on a row opens a popup dialog displaying transaction details.
    Tab and Shift+Tab navigate between rows (unless at the beginning or end of the list).
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
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
        self.doubleClicked.connect(self.activate_action)

    def setModel(self, model):
        if not isinstance(model, ExpenseModel):
            raise TypeError("Expected a ExpenseModel instance.")
        super().setModel(model)
        self._init_section_sizing()

        self.selectionModel().selectionChanged.connect(signals.categorySelectionChanged)
        self.model().modelAboutToBeReset.connect(signals.categorySelectionChanged)
        self.model().modelReset.connect(signals.categorySelectionChanged)

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
    def activate_action(self, index: QtCore.QModelIndex) -> None:
        """
        Slot called on double-clicking or pressing Enter on a row.
        Opens a popup dialog displaying transaction details for the selected category.
        """
        from .. import ui

        if not index.isValid():
            return

        row = index.row()

        if ui.parent() is None:
            return

        if ui.parent().transactions_view is None:
            ui.parent().transactions_view = TransactionsDialog(parent=ui.parent())
        elif ui.parent().transactions_view.isVisible():
            ui.parent().transactions_view.raise_()
            return

        ui.parent().transactions_view.show()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            index = self.currentIndex()
            if index.isValid():
                self.activate_action(index)
            return
        if key == QtCore.Qt.Key_Tab:
            current = self.currentIndex()
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                if current.isValid() and current.row() > 0:
                    new_index = self.model().index(current.row() - 1, current.column())
                    self.setCurrentIndex(new_index)
                    return
            else:
                if current.isValid() and current.row() < self.model().rowCount() - 1:
                    new_index = self.model().index(current.row() + 1, current.column())
                    self.setCurrentIndex(new_index)
                    return
        super().keyPressEvent(event)


class TransactionsView(QtWidgets.QTableView):
    """
    TransactionsView is a custom QTableView for displaying transaction data.

    It configures selection, sizing, and header behavior for an optimal display of the transactions table.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        self.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.setShowGrid(True)
        self.setAlternatingRowColors(False)
        self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)

    def sizeHint(self) -> QtCore.QSize:
        """Returns the preferred size for the view."""
        return QtCore.QSize(800, 400)

    def _init_header(self) -> None:
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
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
