"""
log/view.py
"""

from PySide6 import QtCore, QtWidgets

from .model import LogFilterProxyModel, Columns
from .model import LogTableModel


class LogTableView(QtWidgets.QTableView):
    """A QTableView displaying log messages from LogTableModel."""

    def __init__(self, parent=None):
        """Initializes the log table view."""
        super().__init__(parent=parent)
        self.setWordWrap(True)

        self._init_model()
        self._init_headers()
        self._init_actions()
        self._connect_signals()

    def _init_model(self):
        """Creates and sets the LogTableModel through a filter proxy."""
        proxy = LogFilterProxyModel(self)
        model = LogTableModel(parent=self)
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setModel(proxy)

    def _init_headers(self):
        """Configures column headers and resizing."""
        header = self.horizontalHeader()
        header.setSectionResizeMode(Columns.Date.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Module.value, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Level, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Message.value, QtWidgets.QHeaderView.Stretch)

        self.setSortingEnabled(True)
        self.sortByColumn(Columns.Date, QtCore.Qt.DescendingOrder)

        header = self.verticalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setHidden(True)

    def _init_actions(self):
        """Initializes actions (stub)."""
        pass

    def _connect_signals(self):
        """Connects signals and slots for model updates."""
        self.model().rowsInserted.connect(self._on_rows_inserted)

    @QtCore.Slot(QtCore.QModelIndex, int, int)
    def _on_rows_inserted(self, parent_index, start, end):
        """Resize rows after insert to accommodate new entries."""
        self.resizeRowsToContents()
        self.scrollToBottom()
