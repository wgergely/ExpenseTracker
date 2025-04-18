"""
"""
from PySide6 import QtWidgets, QtGui, QtCore

from .model import PresetsModel


class PresetsListView(QtWidgets.QListView):
    """List‑view controller for the project presets."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _init_model(self) -> None:
        model = PresetsModel(self)
        self.setModel(model)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

    def _init_actions(self) -> None:
        @QtCore.Slot()
        def add_preset() -> None:
            name, ok = QtWidgets.QInputDialog.getText(
                self, 'New Preset', 'Preset name:')
            if not ok:
                return
            if not name.strip():
                return
            if not self.model().add_preset(name.strip()):
                QtWidgets.QMessageBox.warning(self, 'Add Preset',
                                              'Failed to create preset.')

        action = QtGui.QAction('Save presets', self)
        action.setShortcut('Ctrl+Shift+S')
        action.setStatusTip('Save current settings as a new preset')
        action.triggered.connect(add_preset)
        self.addAction(action)

        # self._act_add = QtGui.QAction('Add', self)
        # self._act_remove = QtGui.QAction('Remove', self)
        # self._act_rename = QtGui.QAction('Rename', self)
        # self._act_activate = QtGui.QAction('Activate', self)

    def _connect_signals(self) -> None:
        pass
        self._act_add.triggered.connect(self.add_preset)
        self._act_remove.triggered.connect(self.remove_preset)
        self._act_rename.triggered.connect(self.rename_preset)
        self._act_activate.triggered.connect(self.activate_preset)

        self.activated.connect(self.activate_preset)

    @QtCore.Slot()
    def remove_preset(self) -> None:
        row = self._current_row()
        if row is None:
            return
        reply = QtWidgets.QMessageBox.question(
            self, 'Remove Preset',
            'Remove selected preset?', QtWidgets.QMessageBox.Yes,
            QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            if not self._model.remove_preset(row):
                QtWidgets.QMessageBox.warning(self, 'Remove Preset',
                                              'Failed to remove preset.')

    @QtCore.Slot()
    def rename_preset(self) -> None:
        index = self.currentIndex()
        if not index.isValid():
            return
        current_name = index.data()
        name, ok = QtWidgets.QInputDialog.getText(
            self, 'Rename Preset', 'New name:', text=current_name)
        if ok and name.strip() and name != current_name:
            if not self._model.setData(index, name.strip(),
                                       QtCore.Qt.EditRole):
                QtWidgets.QMessageBox.warning(self, 'Rename Preset',
                                              'Failed to rename preset.')

    @QtCore.Slot()
    def activate_preset(self, _index: QtCore.QModelIndex | bool = False) -> None:
        row = self._current_row()
        if row is None:
            return
        if not self._model.activate_preset(row):
            QtWidgets.QMessageBox.warning(self, 'Activate Preset',
                                          'Activation failed.')

    def _current_row(self) -> int | None:
        index = self.currentIndex()
        if not index.isValid():
            return None
        return index.row()


class PresetsPopup(QtWidgets.QFrame):
    """Popup wrapper around PresetsListView.

    Call ``show_at(widget)`` to display the popup at *widget*’s bottom‑left.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(
            parent,
            QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.NoDropShadowWindowHint,
        )
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(PresetsListView(self))
        self.setMinimumSize(250, 200)

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #

    def show_at(self, anchor: QtWidgets.QWidget) -> None:
        """Display the popup beneath *anchor*."""
        global_pos = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height()))
        self.move(global_pos)
        self.show()
