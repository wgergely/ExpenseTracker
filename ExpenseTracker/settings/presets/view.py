"""
"""
import logging
from typing import Optional

from PySide6 import QtWidgets, QtGui, QtCore

from .lib import PresetType
from .model import PresetModel, PresetsSortFilterProxyModel, Columns
from ...ui import ui


class PresetsListDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate for rendering preset items in the list view."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem,
              index: QtCore.QModelIndex) -> None:
        super().paint(painter, option, index)

    def createEditor(self, parent: QtWidgets.QWidget, option: QtWidgets.QStyleOptionViewItem,
                     index: QtCore.QModelIndex) -> Optional[QtWidgets.QWidget]:
        if index.column() == Columns.Name:
            editor = QtWidgets.QLineEdit(parent=parent)
            return editor
        if index.column() == Columns.Description:
            editor = QtWidgets.QLineEdit(parent=parent)
            return editor
        return None

    def setEditorData(self, editor: QtWidgets.QWidget, index: QtCore.QModelIndex) -> None:
        if index.column() == Columns.Name:
            value = index.data(QtCore.Qt.EditRole)
            if isinstance(value, str):
                editor.setText(value)
                return

        if index.column() == Columns.Description:
            value = index.data(QtCore.Qt.EditRole)
            if isinstance(value, str):
                editor.setText(value)
                return

    def updateEditorGeometry(self, editor, option, index):
        col = index.column()
        if col in (Columns.Name, Columns.Description):
            editor.setGeometry(option.rect)
            editor.setStyleSheet(f'height: {option.rect.height()}px;')


class PresetsListView(QtWidgets.QTableView):
    """List‑view controller for the project presets."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        # disable context menu (we'll provide actions in wrapper)
        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        self.setItemDelegate(PresetsListDelegate(self))

        self.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked |
                             QtWidgets.QAbstractItemView.EditKeyPressed)


        self._init_model()
        self._init_header()
        self._init_actions()
        self._connect_signals()

    def _init_model(self) -> None:
        proxy = PresetsSortFilterProxyModel(self)
        model = PresetModel(self)
        proxy.setSourceModel(model)
        self.setModel(proxy)

    def _init_header(self) -> None:
        # configure headers: status auto-size, others stretch
        header = self.horizontalHeader()
        header.setSectionResizeMode(Columns.Status, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Name, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(Columns.Description, QtWidgets.QHeaderView.Stretch)

        header = self.verticalHeader()
        header.setDefaultSectionSize(ui.Size.RowHeight(1.0))

    def _init_actions(self) -> None:
        @QtCore.Slot()
        def add_preset() -> None:
            name, ok = QtWidgets.QInputDialog.getText(
                self, 'Save Preset', 'Preset name:')
            if not ok:
                logging.debug('Add preset cancelled')
                return
            if not name.strip():
                logging.warning('Add preset: empty name, ignoring.')
                return
            try:
                r = self.model().sourceModel().add_preset(name.strip())
                if not r:
                    QtWidgets.QMessageBox.warning(self, 'Add Preset',
                                                  'Failed to create preset.')
            except Exception as ex:
                logging.error(f'Failed to add preset: {ex}')
                QtWidgets.QMessageBox.critical(
                    self, 'Add Preset', f'Failed to create preset: {ex}')
                return

        action = QtGui.QAction('New Preset...', self)
        action.setShortcut('alt+n')
        action.setIcon(ui.get_icon('btn_fileadd'))
        action.setStatusTip('Save current settings as a new preset')
        action.triggered.connect(add_preset)
        self.addAction(action)

    def _connect_signals(self) -> None:
        @QtCore.Slot(QtCore.QModelIndex)
        def activated(index: QtCore.QModelIndex) -> None:
            if not index.isValid():
                return

            item = index.data(QtCore.Qt.UserRole + 2)
            if not item:
                return

            if item.type is not PresetType.Active:
                return

            # open settings
            from .. import settings
            settings.show_settings_widget()


        self.activated.connect(activated)


class PresetsPopup(QtWidgets.QFrame):
    """Popup wrapper around PresetsListView.

    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)

        self.setWindowFlags(
            QtCore.Qt.Popup |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.NoDropShadowWindowHint
        )

        self._create_ui()
        self._connect_signals()

    def _create_ui(self) -> None:
        QtWidgets.QVBoxLayout(self)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.view = PresetsListView(self)
        self.layout().addWidget(self.view)

    def show_at(self, anchor: QtWidgets.QWidget) -> None:
        """Display the popup beneath *anchor*."""
        global_pos = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height()))
        self.move(global_pos)
        self.show()
