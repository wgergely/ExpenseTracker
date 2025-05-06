"""
Transaction preview view for displaying full details of a single transaction.
"""

from decimal import Decimal

from PySide6 import QtWidgets, QtCore

from ...core.database import database
from ...ui import ui
from ...ui.actions import signals
from ...ui.dockable_widget import DockableWidget
from ...ui.ui import Color, Size


class AmountLabel(QtWidgets.QLabel):
    """Special label to display the transaction amount prominently."""

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent)

    def set_amount(self, amount: Decimal) -> None:
        """Configure text, font, size, color, and alignment based on amount."""
        self.setText(f'{amount:.2f}')
        font, _ = ui.Font.BlackFont(Size.LargeText(1.3))
        self.setFont(font)
        side = Size.DefaultHeight(0.5)
        self.setFixedSize(side, side)
        color_css = Color.Red(qss=True) if amount < 0 else Color.Green(qss=True)
        self.setStyleSheet(f'color: {color_css}')
        self.setAlignment(QtCore.Qt.AlignCenter)


class TransactionPreviewView(DockableWidget):
    """Dockable widget that shows a detailed preview of a selected transaction."""

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__('Transaction Preview', parent=parent,
                         min_width=Size.DefaultWidth(1.0))
        self.amount_label: AmountLabel
        self.form_layout: QtWidgets.QFormLayout

        self._create_ui()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self) -> None:
        self.amount_label = AmountLabel()

        self.form_widget = QtWidgets.QWidget()
        self.form_layout = QtWidgets.QFormLayout(self.form_widget)

        container = QtWidgets.QWidget()
        m = Size.Margin(1.0)
        container.setContentsMargins(m, m, m, m)
        vlay = QtWidgets.QVBoxLayout(container)
        vlay.addWidget(self.amount_label, alignment=QtCore.Qt.AlignCenter)
        vlay.addWidget(self.form_widget)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)

        # Set the scroll area as the dock widget's central widget
        self.setWidget(scroll)

    def _init_actions(self) -> None:
        pass

    def _connect_signals(self) -> None:
        signals.transactionItemSelected.connect(self._on_transaction_selected)

    @QtCore.Slot(int)
    def _on_transaction_selected(self, tx_id: int) -> None:
        """Load or clear the preview, and show/hide the dock accordingly."""
        if tx_id and tx_id > 0:
            self.init_data(tx_id)
            self.show()
        else:
            self.clear_data()
            self.hide()

    def init_data(self, tx_id: int) -> None:
        """Fetch the transaction by ID and populate the UI."""
        # Fetch the transaction record via DatabaseAPI
        record = database.get_row(tx_id)
        # Clear any existing UI contents
        self.clear_data()
        if not record:
            return

        # Amount at top
        amount_val = Decimal(record.get('amount') or 0)
        self.amount_label.set_amount(amount_val)

        # Date first in form
        date_val = record.get('date')
        if hasattr(date_val, 'strftime'):
            date_str = date_val.strftime('%Y-%m-%d')
        else:
            date_str = str(date_val)
        self.form_layout.addRow('Date', QtWidgets.QLabel(date_str))

        # Other fields
        for col, val in record.items():
            if col in ('amount', 'date'):
                continue
            self.form_layout.addRow(col.title(), QtWidgets.QLabel(str(val)))

    def clear_data(self) -> None:
        """Clear the amount label and remove all form rows."""
        self.amount_label.clear()
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)
