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
        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        self.setItemDelegate(PresetsListDelegate(self))

        self.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked |
                             QtWidgets.QAbstractItemView.EditKeyPressed)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.viewport().setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.viewport().setAttribute(QtCore.Qt.WA_TranslucentBackground, True)

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
        header.setSectionResizeMode(Columns.Name, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(Columns.Description, QtWidgets.QHeaderView.Stretch)

        header = self.verticalHeader()
        header.setDefaultSectionSize(ui.Size.RowHeight(1.0))
        header.setVisible(False)

        try:
            self.setCornerButtonEnabled(False)
        except AttributeError:
            pass

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

        action = QtGui.QAction('Save Current Configuration...', self)
        action.setShortcut('alt+n')
        action.setIcon(ui.get_icon('btn_add', color=ui.Color.Green()))
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

            if item.type is PresetType.Active:
                from .. import settings
                settings.show_settings_widget()
            else:
                # Disallow activating out-of-date presets
                if item.is_out_of_date:
                    QtWidgets.QMessageBox.warning(
                        self,
                        'Activate Preset',
                        f'Preset \'{item.name}\' is out of date and cannot be activated.'
                        ' Please save the changes it before activating.'
                    )
                    return
                if not item or not item.is_saved:
                    logging.warning('Activate preset: item not saved')
                    return
                try:
                    self.model().sourceModel().api().activate(item)
                except Exception as ex:
                    QtWidgets.QMessageBox.critical(
                        self, 'Activate Preset', f'Failed to activate preset: {ex}')

        self.activated.connect(activated)


class PresetsPopup(QtWidgets.QDialog):
    """Popup wrapper around PresetsListView.

    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.toolbar = None
        self.view = None

        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._create_ui()
        self._init_actions()
        self._connect_signals()

    def _create_ui(self) -> None:
        QtWidgets.QVBoxLayout(self)
        o = ui.Size.Margin(0.5)

        self.layout().setContentsMargins(o, o, o, o)
        self.layout().setSpacing(o)

        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.toolbar.setMovable(False)
        self.layout().addWidget(self.toolbar, 1)

        self.view = PresetsListView(self)
        self.layout().addWidget(self.view)

    def show_at(self, widget: QtWidgets.QWidget) -> None:
        """Display the popup beneath *anchor*."""
        global_pos = widget.mapToGlobal(QtCore.QPoint(0, widget.height()))
        self.move(global_pos)
        self.show()

    def _init_actions(self) -> None:
        """Initialize toolbar actions for managing presets."""
        proxy = self.view.model()
        model = proxy.sourceModel()

        # New Preset
        @QtCore.Slot()
        def new_preset() -> None:
            name, ok = QtWidgets.QInputDialog.getText(
                self, 'Save Current Ledger', 'Preset name:')
            if not ok or not name.strip():
                return
            try:
                model.api().new(name.strip())
            except Exception as ex:
                QtWidgets.QMessageBox.critical(
                    self, 'Save Current Ledger', f'Failed to save preset: {ex}')

        action = QtGui.QAction('Save Current Ledger', self)
        action.setShortcut('Ctrl+N')
        action.setIcon(ui.get_icon('btn_add'))
        action.setStatusTip('Create a new preset from current settings')
        action.triggered.connect(new_preset)
        self.toolbar.addAction(action)
        self.addAction(action)

        # Delete Preset
        @QtCore.Slot()
        def delete_preset() -> None:
            if not self.view.selectionModel().hasSelection():
                return
            index = next((f for f in self.view.selectionModel().selectedIndexes()), QtCore.QModelIndex())
            if not index.isValid():
                return

            src = proxy.mapToSource(index)
            item = src.data(QtCore.Qt.UserRole + 2)

            if not item:
                return

            if item.type is PresetType.Active:
                QtWidgets.QMessageBox.critical(
                    self, 'Delete Preset', 'Cannot delete active preset.')
                return

            r = QtWidgets.QMessageBox.question(
                self, 'Delete Preset',
                f'Delete preset "{item.name}"? This cannot be undone.',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )

            if r != QtWidgets.QMessageBox.Yes:
                return
            try:
                model.api().remove(item)
            except Exception as ex:
                QtWidgets.QMessageBox.critical(
                    self, 'Delete Preset', f'Failed to delete preset: {ex}')

        action = QtGui.QAction('Delete', self)
        action.setShortcut('Delete')
        action.setStatusTip('Delete selected preset')
        action.triggered.connect(delete_preset)
        self.toolbar.addAction(action)
        self.addAction(action)

        # separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        # Activate Preset
        @QtCore.Slot()
        def activate_preset() -> None:
            if not self.view.selectionModel().hasSelection():
                return
            index = next((f for f in self.view.selectionModel().selectedIndexes()), QtCore.QModelIndex())
            if not index.isValid():
                return

            src = proxy.mapToSource(index)
            item = src.data(QtCore.Qt.UserRole + 2)

            if item.type is PresetType.Active:
                logging.warning('Activate preset: item is already active')
                return

            if not item or not item.is_saved:
                return

            try:
                model.api().activate(item)
            except Exception as ex:
                QtWidgets.QMessageBox.critical(
                    self, 'Activate Preset', f'Failed to activate preset: {ex}')

        action = QtGui.QAction('Activate', self)
        action.setShortcut('Ctrl+A')
        action.setIcon(ui.get_icon('btn_active'))
        action.setStatusTip('Activate selected preset')
        action.triggered.connect(activate_preset)
        self.toolbar.addAction(action)
        self.addAction(action)

        # separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        # Rename Preset
        @QtCore.Slot()
        def rename_preset() -> None:
            if not self.view.selectionModel().hasSelection():
                return
            index = next((f for f in self.view.selectionModel().selectedIndexes()), QtCore.QModelIndex())
            if not index.isValid():
                return

            src = proxy.mapToSource(index)
            item = src.data(QtCore.Qt.UserRole + 2)
            if not item:
                return
            new_name, ok = QtWidgets.QInputDialog.getText(
                self, 'Rename Preset', 'New name:', text=item.name)
            if not ok or not new_name.strip():
                return
            try:
                model.api().rename(item, new_name.strip())
            except Exception as ex:
                QtWidgets.QMessageBox.critical(
                    self, 'Rename Preset', f'Failed to rename preset: {ex}')

        action = QtGui.QAction('Rename', self)
        action.setShortcut('F2')
        action.setStatusTip('Rename selected preset')
        action.triggered.connect(rename_preset)
        self.addAction(action)

        # Duplicate Preset
        @QtCore.Slot()
        def duplicate_preset() -> None:
            if not self.view.selectionModel().hasSelection():
                return
            index = next((f for f in self.view.selectionModel().selectedIndexes()), QtCore.QModelIndex())
            if not index.isValid():
                return

            src = proxy.mapToSource(index)
            item = src.data(QtCore.Qt.UserRole + 2)

            if item.type is PresetType.Active:
                QtWidgets.QMessageBox.critical(
                    self, 'Duplicate Preset', 'Cannot duplicate active preset.')
                return

            if not item or not item.is_saved:
                return

            new_name, ok = QtWidgets.QInputDialog.getText(
                self, 'Duplicate Preset', 'New name:')

            if not ok or not new_name.strip():
                return

            try:
                model.api().duplicate(item, new_name.strip())
            except Exception as ex:
                QtWidgets.QMessageBox.critical(
                    self, 'Duplicate Preset', f'Failed to duplicate preset: {ex}')

        action = QtGui.QAction('Duplicate', self)
        action.setShortcut('Ctrl+D')
        action.setIcon(ui.get_icon('btn_fileadd'))
        action.setStatusTip('Duplicate selected preset')
        action.triggered.connect(duplicate_preset)
        self.toolbar.addAction(action)
        self.addAction(action)

        # separator
        action = QtGui.QAction(self)
        action.setSeparator(True)
        action.setEnabled(False)
        self.toolbar.addAction(action)
        self.addAction(action)

        # Update Preset snapshot
        @QtCore.Slot()
        def save_preset() -> None:
            if not self.view.selectionModel().hasSelection():
                return
            index = next((f for f in self.view.selectionModel().selectedIndexes()), QtCore.QModelIndex())
            if not index.isValid():
                return

            src = proxy.mapToSource(index)
            item = src.data(QtCore.Qt.UserRole + 2)

            if item.type is PresetType.Active:
                QtWidgets.QMessageBox.critical(
                    self, 'Save Preset', 'Cannot save active preset.')
                return

            if not item or not item.is_saved or not item.is_active:
                logging.warning('Save preset: item not saved or not active')
                return

            try:
                model.api().update(item)
            except Exception as ex:
                QtWidgets.QMessageBox.critical(
                    self, 'Save Preset', f'Failed to save preset changes: {ex}')

        action = QtGui.QAction('Save Changes', self)
        action.setShortcut('Ctrl+S')
        action.setIcon(ui.get_icon('btn_sync'))
        action.setStatusTip('Save change to preset')
        action.triggered.connect(save_preset)
        self.toolbar.addAction(action)
        self.addAction(action)

    def _connect_signals(self) -> None:
        """Connect signals to the view."""
        # No signals to connect for now
        pass
