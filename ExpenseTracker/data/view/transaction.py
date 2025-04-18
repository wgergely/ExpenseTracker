from PySide6 import QtWidgets, QtCore, QtGui

from ..model.transaction import TransactionsModel, TransactionsSortFilterProxyModel, Columns
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

        self._create_ui()

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
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.setWordWrap(True)

        self.viewport().setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.viewport().setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.MinimumExpanding
        )

        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _init_model(self) -> None:
        model = TransactionsModel()
        proxy = TransactionsSortFilterProxyModel(self)
        proxy.setSourceModel(model)
        self.setModel(proxy)

        self._init_section_sizing()

        self.setSortingEnabled(True)
        self.sortByColumn(Columns.Amount.value, QtCore.Qt.AscendingOrder)

    def _init_actions(self) -> None:
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        action = QtGui.QAction('Sort by Date', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('alt+1')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Date.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Amount', self)
        action.setCheckable(True)
        action.setShortcut('alt+2')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Amount.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Description', self)
        action.setCheckable(True)
        action.setShortcut('alt+3')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Description.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Category', self)
        action.setCheckable(True)
        action.setShortcut('alt+4')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Category.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Account', self)
        action.setCheckable(True)
        action.setShortcut('alt+5')
        action.triggered.connect(lambda: self.sortByColumn(Columns.Account.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        # separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        action = QtGui.QAction('Sort Ascending', self)
        action.setCheckable(True)
        action.setShortcut('alt+up')
        action.triggered.connect(lambda: self.sortByColumn(self.model().sortColumn(), QtCore.Qt.AscendingOrder))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort Descending', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('alt+down')
        action.triggered.connect(lambda: self.sortByColumn(self.model().sortColumn(), QtCore.Qt.DescendingOrder))
        action_group.addAction(action)
        self.addAction(action)

        # separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.addAction(action)

        @QtCore.Slot()
        def set_search_filter():
            # popup up a dialog to set the search filter
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle('Set Search Filter')
            dialog.setModal(True)
            dialog.setSizeGripEnabled(True)
            dialog.setMinimumSize(
                ui.Size.DefaultWidth(0.5),
                ui.Size.RowHeight(1.0)
            )
            dialog.setSizePolicy(
                QtWidgets.QSizePolicy.MinimumExpanding,
                QtWidgets.QSizePolicy.MinimumExpanding
            )
            dialog.setWindowFlags(dialog.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

            QtWidgets.QVBoxLayout(dialog)
            o = ui.Size.Margin(1.0)
            dialog.layout().setContentsMargins(o, o, o, o)
            dialog.layout().setSpacing(0)
            dialog.layout().addWidget(QtWidgets.QLabel('Search Filter:'), 0)
            line_edit = QtWidgets.QLineEdit(dialog)
            line_edit.setPlaceholderText('Enter search filter')
            line_edit.setSizePolicy(
                QtWidgets.QSizePolicy.MinimumExpanding,
                QtWidgets.QSizePolicy.MinimumExpanding
            )
            dialog.layout().addWidget(line_edit, 1)

            button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
                                                    dialog)
            button_box.setSizePolicy(
                QtWidgets.QSizePolicy.MinimumExpanding,
                QtWidgets.QSizePolicy.MinimumExpanding
            )
            button_box.button(QtWidgets.QDialogButtonBox.Ok).setText('Apply')
            button_box.button(QtWidgets.QDialogButtonBox.Cancel).setText('Close')
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            dialog.layout().addWidget(button_box, 1)

            line_edit.setText(self.model().filter_string())

            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                filter_text = line_edit.text()
                if filter_text:
                    self.model().set_filter_string(filter_text)
                else:
                    self.model().set_filter_string('')

        action = QtGui.QAction('Find...', self)
        action.setShortcut('ctrl+f')
        action.triggered.connect(set_search_filter)
        self.addAction(action)

    @QtCore.Slot()
    def _init_section_sizing(self) -> None:
        header = self.horizontalHeader()
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.setStretchLastSection(False)

        header.setSectionResizeMode(Columns.Account.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Date.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Amount.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Description.value, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(Columns.Category.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Amount.value, QtWidgets.QHeaderView.Interactive)

        header.setSortIndicatorShown(True)
        header.setSortIndicator(Columns.Amount.value, QtCore.Qt.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSectionsMovable(False)

        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        header.setDefaultSectionSize(ui.Size.RowHeight(1.8))
        header.setHidden(True)

    def _connect_signals(self):
        self.model().sourceModel().modelReset.connect(
            lambda: self.model().sort(self.model().sortColumn(), self.model().sortOrder()))
        self.model().sourceModel().modelReset.connect(self.resizeColumnsToContents)
