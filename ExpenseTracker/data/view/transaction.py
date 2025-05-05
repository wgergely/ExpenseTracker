"""Transaction view and delegates for editing and displaying transactions.

This module provides:
    - PopupCombobox: adaptive-width combo box for category selection
    - CategoryDelegate: custom delegate with category icons and pending-edit highlights
    - TransactionsView: table view for transaction records with sorting and filtering
    - TransactionsWidget: dockable widget for viewing transactions with sync controls
"""
import logging
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui

from ..model.transaction import TransactionsModel, TransactionsSortFilterProxyModel, Columns
from ...core.sync import sync
from ...settings import lib
from ...ui import ui
from ...ui.dockable_widget import DockableWidget
from ...ui.ui import get_icon, CategoryIconEngine, Color, Size


class PopupCombobox(QtWidgets.QComboBox):
    """Combo box that expands its popup to fit content width."""

    def showPopup(self):

        fm = self.fontMetrics()
        max_text = 0
        for i in range(self.count()):
            text = self.itemText(i)
            w = fm.horizontalAdvance(text)
            if w > max_text:
                max_text = w
        icon_w = self.iconSize().width()
        # add padding
        total_w = max_text + icon_w + ui.Size.Margin(1.0)
        self.view().setMinimumWidth(total_w)
        super().showPopup()


class CategoryDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate providing a dropdown with category icons and highlighting pending edits."""

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        editor = PopupCombobox(parent=parent)
        cats = lib.settings.get_section('categories') or {}
        for key, info in cats.items():
            icon_name = info.get('icon', 'cat_unclassified')
            hex_color = info.get('color', Color.Text().name(QtGui.QColor.HexRgb))
            qcolor = QtGui.QColor(hex_color)
            icon = get_icon(icon_name, color=qcolor, engine=CategoryIconEngine)
            display = info.get('display_name') or key
            editor.addItem(icon, display, userData=key)
        # automatically open the dropdown on single-click
        QtCore.QTimer.singleShot(0, editor.showPopup)

        def on_activated(idx: int) -> None:
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.NoHint)

        editor.activated.connect(on_activated)

        return editor

    def setEditorData(self, editor: QtWidgets.QComboBox, index: QtCore.QModelIndex) -> None:
        value = index.data(QtCore.Qt.EditRole)
        for i in range(editor.count()):
            if editor.itemData(i) == value:
                editor.setCurrentIndex(i)
                return

    def setModelData(self, editor: QtWidgets.QComboBox, model: QtCore.QAbstractItemModel,
                     index: QtCore.QModelIndex) -> None:
        new_val = editor.currentData()
        model.setData(index, new_val, QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                             index: QtCore.QModelIndex) -> None:
        # match the cell geometry including height
        editor.setGeometry(option.rect)
        editor.setStyleSheet(f'height: {option.rect.height()}px;')

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:
        super().paint(painter, option, index)
        pending = False
        try:
            model = index.model()
            if isinstance(model, QtCore.QSortFilterProxyModel):
                src_index = model.mapToSource(index)
                src_model = model.sourceModel()
            else:
                src_index = index
                src_model = model
            last_col = len(lib.TRANSACTION_DATA_COLUMNS) - 1
            lid = src_model.index(src_index.row(), last_col).data(QtCore.Qt.EditRole)
            pending = any(op.local_id == lid and op.column == 'category' for op in sync.get_queued_ops())
        except Exception:
            pass
        if pending:
            pen = QtGui.QPen(Color.Yellow())
            pen.setWidthF(Size.Separator(2.0))
            painter.save()
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()
        # also draw a red border for failed edits
        try:
            # map through proxy to source model
            model = index.model()
            if isinstance(model, QtCore.QSortFilterProxyModel):
                src_index = model.mapToSource(index)
                src_model = model.sourceModel()
            else:
                src_index = index
                src_model = model
            if hasattr(src_model, '_failed_cells'):
                key = (src_index.row(), src_index.column())
                if key in src_model._failed_cells:
                    pen = QtGui.QPen(Color.Red())
                    pen.setWidthF(Size.Separator(2.0))
                    painter.save()
                    painter.setPen(pen)
                    painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
                    painter.restore()
        except Exception:
            pass


class TransactionsView(QtWidgets.QTableView):
    """Table view for displaying and interacting with transaction records."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent=parent)

        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        # Allow editing of editable cells via double-click or pressing F2
        # Enable editing on single click, key press, double click, etc.
        self.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.setShowGrid(True)
        self.setAlternatingRowColors(False)

        self.setWordWrap(True)
        self.setTextElideMode(QtCore.Qt.ElideNone)

        self.viewport().setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.viewport().setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Minimum
        )

        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _init_model(self) -> None:
        model = TransactionsModel()
        proxy = TransactionsSortFilterProxyModel(self)
        proxy.setSourceModel(model)
        self.setModel(proxy)

        # category column handles pending and failure highlights
        delegate = CategoryDelegate(self)
        self.setItemDelegateForColumn(Columns.Category.value, delegate)

        self._init_section_sizing()

        self.setSortingEnabled(True)
        self.sortByColumn(Columns.Amount.value, QtCore.Qt.AscendingOrder)

        last_col = len(lib.TRANSACTION_DATA_COLUMNS) - 1
        self.setColumnHidden(last_col, True)

    def _init_actions(self) -> None:
        action_group = QtGui.QActionGroup(self)
        action_group.setExclusive(True)

        action = QtGui.QAction('Sort by Date', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('Alt+1')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda: self.sortByColumn(Columns.Date.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Amount', self)
        action.setCheckable(True)
        action.setShortcut('Alt+2')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda: self.sortByColumn(Columns.Amount.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Description', self)
        action.setCheckable(True)
        action.setShortcut('Alt+3')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda: self.sortByColumn(Columns.Description.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Category', self)
        action.setCheckable(True)
        action.setShortcut('Alt+4')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda: self.sortByColumn(Columns.Category.value, self.model().sortOrder()))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort by Account', self)
        action.setCheckable(True)
        action.setShortcut('Alt+5')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
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
        action.setShortcut('Alt+up')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(lambda: self.sortByColumn(self.model().sortColumn(), QtCore.Qt.AscendingOrder))
        action_group.addAction(action)
        self.addAction(action)

        action = QtGui.QAction('Sort Descending', self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setShortcut('Alt+down')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
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
        action.setShortcut('Ctrl+f')
        action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
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
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setDefaultSectionSize(ui.Size.RowHeight(2.0))
        header.setMinimumSectionSize(ui.Size.RowHeight(2.0))
        header.setMaximumSectionSize(ui.Size.RowHeight(4.0))
        header.setHidden(True)

    def _connect_signals(self):
        self.model().sourceModel().modelReset.connect(
            lambda: self.model().sort(self.model().sortColumn(), self.model().sortOrder()))

        @QtCore.Slot()
        def resize_columns():
            self.resizeColumnToContents(Columns.Description.value)
            self.resizeColumnToContents(Columns.Amount.value)
            self.resizeColumnToContents(Columns.Category.value)
            self.resizeColumnToContents(Columns.Date.value)
            self.resizeColumnToContents(Columns.Account.value)

        self.model().sourceModel().modelReset.connect(resize_columns)
        self.model().sourceModel().dataChanged.connect(resize_columns)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """
        Draw the table view and, if no rows are present, overlay a placeholder message.
        """
        # draw default table
        super().paintEvent(event)
        # show placeholder when no transactions to display
        try:
            model = self.model()
            if model is None or model.rowCount() != 0:
                return
        except Exception:
            return
        # paint overlay text on viewport
        painter = QtGui.QPainter(self.viewport())
        # set font and color for placeholder
        font, _ = ui.Font.MediumFont(ui.Size.MediumText(1.0))
        painter.setFont(font)
        painter.setPen(ui.Color.DisabledText())
        # center the text in the viewport
        rect = self.viewport().rect()
        painter.drawText(rect, QtCore.Qt.AlignCenter, 'No transactions')
        painter.end()


class TransactionsWidget(DockableWidget):
    """Dock widget for displaying transactions with sync status and controls."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__('Transactions', parent=parent, min_width=Size.DefaultWidth(1.0))
        self.setObjectName('ExpenseTrackerTransactionsWidget')

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Preferred
        )

        self.view = None

        self._create_ui()
        self._connect_signals()

        sync.queueChanged.connect(self._on_queue_changed)

    def _connect_signals(self):
        sync.commitFinished.connect(self._on_commit_finished)
        self.sync_button.clicked.connect(sync.commit_queue_async)
        self.view.model().dataChanged.connect(self._update_sync_button)

    def _create_ui(self) -> None:
        content = QtWidgets.QWidget(self)
        content.setProperty('rounded', True)

        QtWidgets.QVBoxLayout(content)

        o = ui.Size.Margin(1.0)
        content.layout().setContentsMargins(o, o, o, o)
        content.layout().setSpacing(o)

        # Transaction table
        self.view = TransactionsView(content)
        content.layout().addWidget(self.view, 1)

        # Pending edits status label (rich text)
        self.status_label = QtWidgets.QLabel('', content)
        self.status_label.setVisible(False)
        self.status_label.setTextFormat(QtCore.Qt.RichText)
        content.layout().addWidget(self.status_label)

        # Button to push queued edits
        self.sync_button = QtWidgets.QPushButton('Push Edits', content)
        self.sync_button.setVisible(False)
        self.sync_button.setEnabled(False)
        content.layout().addWidget(self.sync_button)

        self.setWidget(content)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            ui.Size.DefaultWidth(1.0),
            ui.Size.DefaultHeight(1.0)
        )

    def _update_sync_button(self) -> None:
        # Enable or disable the sync button based on queued edits
        self.sync_button.setEnabled(bool(sync.get_queued_ops()))

    @QtCore.Slot(int)
    def _on_queue_changed(self, count: int) -> None:
        if count > 0:
            self.status_label.setText(f'<b>{count}</b> edit(s) pending')
            self.status_label.setVisible(True)
            self.sync_button.setVisible(True)
            self.sync_button.setEnabled(True)
        else:
            self.status_label.setVisible(False)
            self.sync_button.setVisible(False)

    @QtCore.Slot(object)
    def _on_commit_finished(self, results) -> None:
        # Handle completion of commit, displaying success and error summary
        # Summarize results
        # summarize successes and failures by (local_id, column)
        success_count = sum(1 for ok, _ in results.values() if ok)
        # collect failures and log details
        failures = [(lid, col, msg)
                    for (lid, col), (ok, msg) in results.items()
                    if not ok]
        # log all failures to stderr/log
        for lid, col, msg in failures:
            logging.error(f'Push failed for {col} (ID {lid}): {msg}')
        parts = []
        if success_count:
            parts.append(f'<b>{success_count}</b> edit(s) applied')
        if failures:
            # show only the first failure in UI, summarise others
            first_lid, first_col, first_msg = failures[0]
            failed_count = len(failures)
            parts.append(f'<b>{failed_count}</b> failed: {first_col} (ID {first_lid}): {first_msg}')
            if failed_count > 1:
                parts.append(f'… and {failed_count - 1} other edit(s) failed')
        # Update status label
        text = ' '.join(parts)
        self.status_label.setText(text)
        self.status_label.setVisible(True)
        # Hide sync button after commit
        self.sync_button.setVisible(False)
