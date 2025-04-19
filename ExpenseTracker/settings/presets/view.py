"""
"""
import logging

from PySide6 import QtWidgets, QtGui, QtCore

from .model import PresetsModel, PresetsSortFilterProxyModel
from ...ui import ui


class PresetsListView(QtWidgets.QListView):
    """List‑view controller for the project presets."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent)

        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self._init_model()
        self._init_actions()
        self._connect_signals()

    def _init_model(self) -> None:
        proxy = PresetsSortFilterProxyModel(self)
        model = PresetsModel(self)
        proxy.setSourceModel(model)
        self.setModel(proxy)

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
        pass


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
