from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui

from ..model.transaction import TransactionsModel, TransactionsSortFilterProxyModel, Columns
from ...core.sync import sync_manager
from ...settings import lib
from ...ui import ui
from ...ui.ui import get_icon, CategoryIconEngine, Color, Size


class PopupCombobox(QtWidgets.QComboBox):
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
    """
    A delegate that provides a dropdown editor with category icons and colors,
    and highlights cells with pending edits.
    """

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> QtWidgets.QWidget:
        editor = PopupCombobox(parent)
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
            pending = any(op.local_id == lid and op.column == 'category' for op in sync_manager.get_queued_ops())
        except Exception:
            pass
        if pending:
            pen = QtGui.QPen(Color.Yellow())
            pen.setWidthF(Size.Separator(2.0))
            painter.save()
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(0, 0, -1, -1))
            painter.restore()


class TransactionsView(QtWidgets.QTableView):
    """
    TransactionsView is a custom QTableView for displaying transaction data.

    It configures selection, sizing, and header behavior for an optimal display of the transactions table.
    """

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
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        header.setDefaultSectionSize(ui.Size.RowHeight(2.0))
        header.setMinimumSectionSize(ui.Size.RowHeight(2.0))
        header.setMaximumSectionSize(ui.Size.RowHeight(4.0))
        header.setHidden(True)

    def _connect_signals(self):
        self.model().sourceModel().modelReset.connect(
            lambda: self.model().sort(self.model().sortColumn(), self.model().sortOrder()))
        self.model().sourceModel().modelReset.connect(self.resizeColumnsToContents)


class TransactionsWidget(QtWidgets.QDockWidget):
    """
    TransactionsWidget is a custom dockable widget for displaying transaction data.

    It initializes the view and sets up the layout for displaying transactions.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__('Transactions', parent=parent)
        self.setObjectName('ExpenseTrackerTransactionsWidget')
        self.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable |
            QtWidgets.QDockWidget.DockWidgetFloatable |
            QtWidgets.QDockWidget.DockWidgetClosable
        )

        self.setSizePolicy(
            QtWidgets.QSizePolicy.MinimumExpanding,
            QtWidgets.QSizePolicy.Preferred
        )

        self.view = None

        self._create_ui()
        self._connect_signals()

        sync_manager.queueChanged.connect(self._on_queue_changed)

    def _connect_signals(self):
        sync_manager.commitFinished.connect(self._on_commit_finished)
        self.sync_button.clicked.connect(sync_manager.commit_queue_async)
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
        """Enable or disable the sync button based on queued edits."""
        self.sync_button.setEnabled(bool(sync_manager.get_queued_ops()))

    @QtCore.Slot(int)
    def _on_queue_changed(self, count: int) -> None:
        """
        Show or hide the pending-edits status and button based on queue size.
        """
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
        """Handle completion of commit, displaying success and error summary."""
        # Summarize results
        successes = [lid for lid, (ok, _) in results.items() if ok]
        failures = [(lid, msg) for lid, (ok, msg) in results.items() if not ok]
        parts = []
        if successes:
            parts.append(f'<b>{len(successes)}</b> edit(s) applied')
        if failures:
            parts.append(f'<b>{len(failures)}</b> failed')
            parts.append('<ul>')
            for lid, msg in failures:
                parts.append(f'<li>ID {lid}: {msg}</li>')
            parts.append('</ul>')
        # Update status label
        text = ' '.join(parts)
        self.status_label.setText(text)
        self.status_label.setVisible(True)
        # Hide sync button after commit
        self.sync_button.setVisible(False)
