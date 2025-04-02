"""
MonthlyExpenseView Module

This module provides a custom QTableView (MonthlyExpenseView) for displaying monthly expense data
with a chart-like appearance. Double-clicking a row opens a popup that lists all transactions for
the selected category using the new data layout from the model.
"""

from PySide6 import QtCore, QtWidgets, QtGui
from .model import TransactionsRole, MonthlyExpenseModel


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

    It hides headers, enforces single row selection without outlines, and uses custom delegates
    for a chart-like appearance. Double-clicking any row opens a popup listing transactions for
    the selected category.
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
        Opens a popup dialog listing all transactions for the selected category.
        """
        if not index.isValid():
            return
        model = self.model()
        row = index.row()
        # Retrieve transactions using the custom TransactionsRole from column 2.
        idx = model.index(row, 2)
        transactions = idx.data(TransactionsRole)
        if not transactions:
            return

        # Load ledger.json config to determine which transaction keys to display.
        from ..database.database import load_config
        config = load_config()
        mapping = config.get('data_header_mapping', {})
        # Define display keys (fallback defaults).
        display_keys = {
            'date': 'date',
            'description': 'description',
            'amount': 'amount',
            'account': 'account'
        }
        # If mapping is provided, assume the keys defined in the config are the desired ones.
        for key in display_keys:
            if key in mapping:
                display_keys[key] = key

        # Create a popup dialog.
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle('Transactions')
        layout = QtWidgets.QVBoxLayout(dialog)
        list_widget = QtWidgets.QListWidget(dialog)
        layout.addWidget(list_widget)

        # Populate the list with transaction details.
        for tx in transactions:
            # tx is expected to be a dictionary.
            date_val = tx.get(display_keys['date'], '')
            desc_val = tx.get(display_keys['description'], '')
            amount_val = tx.get(display_keys['amount'], 0)
            account_val = tx.get(display_keys['account'], '')
            try:
                amount_str = f'€{float(amount_val):.2f}'
            except (ValueError, TypeError):
                amount_str = ''
            item_text = f"{date_val} | {desc_val} | {amount_str} | {account_val}"
            list_widget.addItem(QtWidgets.QListWidgetItem(item_text))

        dialog.exec()


class TransactionsView(QtWidgets.QTableView):
    """
    TransactionsView is a custom QTableView for displaying transaction data.
    It is tailored for the TransactionsModel, configuring selection, sizing, and header behavior
    for an optimal, dynamic display of the transactions table.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
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
