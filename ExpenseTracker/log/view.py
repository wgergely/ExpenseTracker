"""Log views and dock widget for displaying and interacting with log messages.

This module provides:
    - LogTableView: table view for formatted log entries
    - LogDockWidget: dockable container with filtering and clear actions
"""
import logging

from PySide6 import QtCore, QtWidgets, QtGui

from . import log
from .model import LogFilterProxyModel, Columns
from .model import LogTableModel, get_handler, LogEntryModel
from ..ui import ui
from ..ui.dockable_widget import DockableWidget


class LogTableView(QtWidgets.QTableView):
    """A QTableView displaying log messages from LogTableModel."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self.setWordWrap(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.setItemDelegate(ui.RoundedRowDelegate(parent=self))
        self.setProperty('noitembackground', True)

        self._init_model()
        self._init_headers()
        self._init_actions()
        self._connect_signals()

    def _init_model(self):
        proxy = LogFilterProxyModel(self)
        model = LogTableModel(parent=self)
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setModel(proxy)

    def _init_headers(self):
        header = self.horizontalHeader()
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        header.setDefaultSectionSize(ui.Size.DefaultWidth(0.3))
        header.setSectionResizeMode(Columns.Date.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Module.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Level, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Message.value, QtWidgets.QHeaderView.Stretch)
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.setSortingEnabled(True)
        self.sortByColumn(Columns.Date, QtCore.Qt.DescendingOrder)

        header = self.verticalHeader()
        header.setDefaultSectionSize(ui.Size.RowHeight(1.0))
        header.setHidden(True)

    def _init_actions(self):
        pass

    def _connect_signals(self):
        # Update view when new rows are added
        self.model().rowsInserted.connect(self.on_rows_inserted)
        # Open detailed view when activated (double-click or Enter key)
        # Only use 'activated' to avoid duplicate dialogs
        self.activated.connect(self.on_entry_activated)

    @QtCore.Slot()
    def on_rows_inserted(self):
        header = self.horizontalHeader()
        sort_col = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        model = self.model()

        # Scroll and select based on sort order
        if sort_col == Columns.Date.value and sort_order == QtCore.Qt.DescendingOrder:
            # newest at top
            self.scrollToTop()
            index = model.index(0, 0)
        else:
            # newest at bottom
            self.scrollToBottom()
            index = model.index(model.rowCount() - 1, 0)

        # Select and ensure visibility
        if index.isValid():
            sel = self.selectionModel()
            sel.clearSelection()
            sel.select(index, QtCore.QItemSelectionModel.ClearAndSelect)
            sel.setCurrentIndex(index, QtCore.QItemSelectionModel.NoUpdate)
            self.scrollTo(index)

    @QtCore.Slot(QtCore.QModelIndex)
    def on_entry_activated(self, index: QtCore.QModelIndex) -> None:
        """Open a dialog showing the full log entry details."""
        if not index.isValid():
            return
        proxy = self.model()
        src_model = proxy.sourceModel()
        # Map proxy index to source model
        src_index = proxy.mapToSource(index)
        try:
            entry = src_model.get_entry(src_index.row())
        except Exception as e:
            logging.warning(f'Failed to retrieve log entry: {e}')
            return
        # Show entry in dialog
        dialog = LogEntryDialog(entry, parent=self.window())
        dialog.exec()

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(0.5)
        )


class LogDockWidget(DockableWidget):
    """Dockable widget for viewing app logs."""

    def __init__(self, parent=None) -> None:
        super().__init__('Logs', parent)
        self.setObjectName('ExpenseTrackerLogDockWidget')

        widget = QtWidgets.QWidget(self)
        widget.setProperty('rounded', True)

        QtWidgets.QVBoxLayout(widget)
        widget.layout().setContentsMargins(0, 0, 0, 0)
        widget.layout().setSpacing(0)

        self.view = LogTableView(widget)
        self.view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        widget.layout().addWidget(self.view, 1)

        self.setWidget(widget)

        self._init_actions()
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.visibilityChanged.connect(self.on_visibility_changed)

    def _init_actions(self) -> None:
        proxy = self.view.model()

        action = QtGui.QAction('App Level', self)
        menu = QtWidgets.QMenu(self)
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        for name, lvl in [
            ('Debug', logging.DEBUG),
            ('Info', logging.INFO),
            ('Warning', logging.WARNING),
            ('Error', logging.ERROR),
            ('Critical', logging.CRITICAL),
        ]:
            act = menu.addAction(name)
            act.setData(lvl)
            act.setCheckable(True)
            if logging.getLogger().level == lvl:
                act.setChecked(True)
            action_group.addAction(act)
        action_group.triggered.connect(lambda a: log.set_logging_level(a.data()))

        action.setMenu(menu)
        action.setToolTip('Set application logging level')
        self.view.addAction(action)

        action = QtGui.QAction('View Filter', self)
        menu = QtWidgets.QMenu(self)
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        for name, lvl in [
            ('Debug', logging.DEBUG),
            ('Info', logging.INFO),
            ('Warning', logging.WARNING),
            ('Error', logging.ERROR),
            ('Critical', logging.CRITICAL),
        ]:
            act = menu.addAction(name)
            act.setData(lvl)
            act.setCheckable(True)
            if proxy.filter_level() == lvl:
                act.setChecked(True)
            action_group.addAction(act)
        action_group.triggered.connect(lambda a: proxy.set_filter_level(a.data()))

        action.setMenu(menu)
        action.setToolTip('Filter view by minimum logging level')
        self.view.addAction(action)

        # Clear logs action
        action = QtGui.QAction('Clear Logs', self)
        action.setIcon(ui.get_icon('btn_delete'))
        action.setToolTip('Clear all log entries')
        action.triggered.connect(self._clear_logs)
        self.view.addAction(action)

    @QtCore.Slot()
    def _clear_logs(self) -> None:
        # Clear underlying log tank
        try:
            handler = get_handler()
            handler.clear_logs()
        except RuntimeError:
            logging.warning('TankHandler not found; cannot clear underlying logs.')
        # Clear model entries
        proxy = self.view.model()
        src = proxy.sourceModel()
        src.clear_logs()

    @QtCore.Slot(bool)
    def on_visibility_changed(self, visible: bool) -> None:
        model = self.view.model().sourceModel()
        if visible:
            model.resume()
        else:
            model.pause()


class LogEntryViewDelegate(ui.RoundedRowDelegate):

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QTextEdit(parent)
        editor.setWordWrapMode(QtGui.QTextOption.WrapAnywhere)
        editor.setAcceptRichText(False)
        editor.setReadOnly(True)
        editor.setFrameStyle(QtWidgets.QFrame.NoFrame)

        return editor

    def setEditorData(self, editor, index):
        value = index.data(QtCore.Qt.EditRole)
        editor.setPlainText(value)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)
        editor.setStyleSheet(f'height: {option.rect.height()}px;')


class LogEntryView(QtWidgets.QTableView):
    """A QTableView displaying a single log entry with auto-sized, wrap-enabled cells."""

    def __init__(self, entry: dict[str, object], parent=None):
        super().__init__(parent=parent)
        self.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        self.setWordWrap(True)
        self.setTextElideMode(QtCore.Qt.ElideNone)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.setItemDelegate(LogEntryViewDelegate(self))
        self.setProperty('noitembackground', True)

        self.setModel(LogEntryModel(entry, parent=self))
        self._init_headers()

    def _init_headers(self) -> None:
        header = self.horizontalHeader()
        header.setHidden(True)
        header.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        header.setDefaultSectionSize(ui.Size.DefaultWidth(0.2))
        header.setMinimumSectionSize(ui.Size.DefaultWidth(0.2))
        header.setMaximumSectionSize(ui.Size.DefaultWidth(0.8))

        header.setSectionResizeMode(Columns.Date.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Module.value, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(Columns.Level, QtWidgets.QHeaderView.Interactive)

        header.setSectionResizeMode(Columns.Message.value, QtWidgets.QHeaderView.Stretch)

        header.setStretchLastSection(True)

        vheader = self.verticalHeader()

        vheader.setDefaultSectionSize(ui.Size.RowHeight(1.0))
        vheader.setMinimumSectionSize(ui.Size.RowHeight(1.0))
        vheader.setMaximumSectionSize(ui.Size.RowHeight(20.0))

        vheader.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        vheader.setHidden(True)


class LogEntryDialog(QtWidgets.QDialog):
    """Dialog to display details for a single log entry."""

    def __init__(self, entry: dict[str, object], parent=None):
        super().__init__(parent)
        self.setWindowTitle('Log Entry Details')
        self.setModal(True)

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        self.setMinimumSize(
            ui.Size.DefaultWidth(0.5),
            ui.Size.DefaultHeight(0.2)
        )
        self.setMaximumSize(
            ui.Size.DefaultWidth(2.0),
            ui.Size.DefaultHeight(2.0)
        )

        self.entry = entry
        self.view = None

        self._create_ui()

        QtCore.QTimer.singleShot(0, self.adjust_view)

    def _create_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = LogEntryView(self.entry, parent=self)
        self.view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        layout.addWidget(self.view)

    @QtCore.Slot()
    def adjust_view(self):
        self.view.resizeColumnsToContents()
        self.view.resizeRowsToContents()

        index = self.view.model().index(0, Columns.Message.value)
        self.view.setCurrentIndex(index)

    def sizeHint(self):
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.5),
            ui.Size.DefaultHeight(0.3)
        )
