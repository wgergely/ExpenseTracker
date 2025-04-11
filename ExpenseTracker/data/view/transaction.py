from PySide6 import QtWidgets, QtCore

from ..model.transaction import TransactionsModel, TransactionsSortFilterProxyModel
from ...ui import ui


class TransactionsWidget(QtWidgets.QDockWidget):
    """
    TransactionsWidget is a custom dockable widget for displaying transaction data.

    It initializes the view and sets up the layout for displaying transactions.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__('Transactions', parent=parent)
        self.setObjectName('ExpenseTrackerTransactionsWidget')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable
        )
        self.setMinimumSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )
        self.view = None
        self.proxy_model = None
        self._create_ui()
        self._init_model()

    def _create_ui(self) -> None:
        content = QtWidgets.QWidget(self)
        QtWidgets.QVBoxLayout(content)

        o = ui.Size.Margin(1.0)
        content.layout().setContentsMargins(o, o, o, o)
        content.layout().setSpacing(o)

        self.view = TransactionsView(content)
        self.view.setObjectName('ExpenseTrackerTransactionsView')
        content.layout().addWidget(self.view, 1)

        self.setWidget(content)

    def _init_model(self) -> None:
        model = TransactionsModel()
        self.proxy_model = TransactionsSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(model)
        self.view.setModel(self.proxy_model)
        self.view.setSortingEnabled(True)
        self.view.horizontalHeader().setSortIndicator(1, QtCore.Qt.DescendingOrder)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )


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
        self.setShowGrid(True)
        self.setAlternatingRowColors(False)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

    def setModel(self, model: QtCore.QAbstractItemModel) -> None:
        """Sets the model for the view and initializes the header."""
        super().setModel(model)
        self.model().modelAboutToBeReset.connect(self._init_headers)
        self.model().modelReset.connect(self._init_headers)

    @QtCore.Slot()
    def _init_headers(self) -> None:
        header = self.horizontalHeader()
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)

        header.setSortIndicatorShown(True)
        header.setSortIndicator(0, QtCore.Qt.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)

        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.8))
        header.setHidden(True)
